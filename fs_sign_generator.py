#!/usr/bin/env python3
"""
Forest Service Sign Generator
Produces SVG preview + DXF for VCarve Pro import.

Sign text syntax:
  //   new trail line (1" gap)
  /    continuation line (1/2" gap)
  >    right arrow
  <    left arrow
  ^    up arrow
  v    down arrow (isolated lowercase v)
  Numbers not preceded by Trail/TR → distance (right-justified)
  BOLD text → trail name (left side)
"""

import re
import math
import sys

# ── Specs (all inches) ──────────────────────────────────────────────────────
BORDER         = 2.0    # border on every side
LETTER_H       = 1.0    # cap height
NEW_LINE_GAP   = 1.0    # gap between // lines
CONT_GAP       = 0.5    # gap between / continuation lines
ARROW_GAP      = 1.0    # space before any arrow
DIST_ARR_GAP   = 1.0    # extra space between distance and a RIGHT arrow
MIN_NAME_DIST  = 1.0    # minimum gap between trail name and distance

ARROW_W        = 0.85   # arrow symbol width  (at 1" height)
ARROW_H        = 1.0    # arrow symbol height

HOLE_DIA       = 0.375  # 3/8" drill
CSINK_DIA      = 0.75   # 3/4" countersink
HOLE_Y_INSET   = 1.0    # 1" from top/bottom
HOLE_APART     = 3.0    # 3" between holes on 4-hole signs
TALL_SIGN_THRESH = 11.0 # height above which we use 4 holes

# ── Highway Gothic Narrow Bold approximate char widths at 1" cap height ─────
CW = {
    'A':0.62,'B':0.58,'C':0.62,'D':0.65,'E':0.52,'F':0.50,'G':0.67,
    'H':0.65,'I':0.22,'J':0.38,'K':0.62,'L':0.50,'M':0.78,'N':0.65,
    'O':0.70,'P':0.55,'Q':0.70,'R':0.60,'S':0.55,'T':0.55,'U':0.65,
    'V':0.62,'W':0.85,'X':0.62,'Y':0.58,'Z':0.58,
    '0':0.58,'1':0.35,'2':0.55,'3':0.55,'4':0.58,'5':0.55,'6':0.58,
    '7':0.52,'8':0.58,'9':0.58,
    '/':0.38,' ':0.25,'-':0.38,'.':0.22,"'":0.20,
}
DEFAULT_CW = 0.55

def tw(text, h=1.0):
    """Estimated text width at height h."""
    return sum(CW.get(c.upper(), DEFAULT_CW) for c in text) * h

# ── Parser ───────────────────────────────────────────────────────────────────
def parse_sign(raw):
    """Return list of line dicts."""
    lines = []
    for major_i, major in enumerate(re.split(r'//', raw)):
        major = major.strip()
        if not major:
            continue
        # Split on / that is NOT between digits (avoids splitting fractions)
        subs = re.split(r'(?<!\d)/(?!\d)', major)
        for sub_i, sub in enumerate(subs):
            sub = sub.strip()
            if not sub:
                continue
            d = _parse_line(sub)
            d['is_continuation'] = sub_i > 0
            lines.append(d)
    return lines

def _parse_line(text):
    d = {'trail': '', 'distance': '', 'arrow': '', 'raw': text}
    s = text.strip()

    # Arrow at START (left/right arrows often lead the line for left-pointing signs)
    if s.startswith('<'):
        d['arrow'] = 'left';  s = s[1:].strip()
    elif s.startswith('>'):
        d['arrow'] = 'right'; s = s[1:].strip()

    # Arrow at END (overrides start if both present, handles ^, v, and trailing > <)
    if not d['arrow']:
        if s.endswith('>'):
            d['arrow'] = 'right';  s = s[:-1].strip()
        elif s.endswith('<'):
            d['arrow'] = 'left';   s = s[:-1].strip()

    if s.endswith('^'):
        d['arrow'] = 'up';     s = s[:-1].strip()
    elif re.search(r'(?<!\S)v\s*$', s):
        d['arrow'] = 'down';   s = re.sub(r'\s+v\s*$', '', s).strip()

    # Distance: fraction or whole number at end.
    # Exclude if preceded by '.' (decimal trail number like "NO. 2.1")
    # or if the preceding word is Trail/TR/NO.
    m = re.search(r'\s+(\d+\s+\d+/\d+|\d+/\d+|\d+)\s*$', s)
    if m:
        before = s[:m.start()].strip()
        char_before_space = s[m.start()-1] if m.start() > 0 else ''
        is_decimal_part = char_before_space == '.'
        is_trail_num = bool(re.search(r'\b(Trail|TR|NO\.)\s*$', before, re.I))
        if not is_decimal_part and not is_trail_num:
            d['distance'] = m.group(1).strip()
            s = before

    d['trail'] = s.strip()
    return d

# ── Layout ───────────────────────────────────────────────────────────────────
def layout(lines):
    """Returns (sign_w, sign_h, [(line_dict, y_top), ...])."""

    # Y positions (top of each text block, 0 = top of sign)
    y = BORDER
    positioned = []
    for i, ln in enumerate(lines):
        if i > 0:
            y += CONT_GAP if ln['is_continuation'] else NEW_LINE_GAP
        positioned.append((ln, y))
        y += LETTER_H
    sign_h = y + BORDER

    # Width: find the widest content line
    max_content_w = 0
    for ln, _ in positioned:
        w = tw(ln['trail'])
        if ln['distance']:
            w += MIN_NAME_DIST + tw(ln['distance'])
        if ln['arrow'] == 'right' and ln['distance']:
            w += DIST_ARR_GAP + ARROW_W
        elif ln['arrow']:
            w += ARROW_GAP + ARROW_W
        max_content_w = max(max_content_w, w)

    sign_w = 2 * BORDER + max_content_w
    return sign_w, sign_h, positioned, max_content_w

# ── Hole positions ────────────────────────────────────────────────────────────
def hole_positions(sign_w, sign_h):
    cx = sign_w / 2
    if sign_h <= TALL_SIGN_THRESH:
        return [
            dict(x=cx, y=HOLE_Y_INSET,           slot=False),
            dict(x=cx, y=sign_h - HOLE_Y_INSET,  slot=False),
        ]
    else:
        half = HOLE_APART / 2
        return [
            dict(x=cx - half, y=HOLE_Y_INSET,          slot=True),
            dict(x=cx + half, y=HOLE_Y_INSET,          slot=True),
            dict(x=cx - half, y=sign_h - HOLE_Y_INSET, slot=False),
            dict(x=cx + half, y=sign_h - HOLE_Y_INSET, slot=False),
        ]

# ── Helpers ──────────────────────────────────────────────────────────────────
def xe(text):
    """Escape text for XML element content."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# ── SVG preview ──────────────────────────────────────────────────────────────
def generate_svg(sign_w, sign_h, positioned, content_w, holes):
    PPI = 96
    W = sign_w * PPI
    H = sign_h * PPI
    right_edge = BORDER + content_w  # right edge of content area

    def px(v): return f'{v * PPI:.2f}'

    # Expand height to accommodate dimension label below sign
    label_h = 28
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
               f'width="{W:.0f}" height="{H + label_h:.0f}" '
               f'viewBox="0 0 {W:.0f} {H + label_h:.0f}">')
    out.append('<defs><style><![CDATA['
               'text{font-family:"Highway Gothic Narrow","Highway Gothic",'
               '"Arial Narrow",sans-serif;font-weight:bold;}'
               ']]></style></defs>')

    # Background
    out.append(f'<rect width="{W:.0f}" height="{H:.0f}" fill="#7B6542"/>')

    b = BORDER * PPI  # used below for positioning

    for ln, y_top in positioned:
        baseline_y = (y_top + LETTER_H * 0.82) * PPI
        fs = LETTER_H * PPI
        is_left = ln['arrow'] == 'left'

        # Arrow — left side for left arrows, right edge for all others
        if ln['arrow']:
            if is_left:
                ax = BORDER * PPI
                ay = y_top * PPI
            else:
                ax = (right_edge - ARROW_W) * PPI
                ay = y_top * PPI
            out.append(_svg_arrow(ln['arrow'], ax, ay, ARROW_W * PPI, ARROW_H * PPI, '#E8D5A3'))

        # Trail name — left (indented past arrow for left-arrow lines)
        if ln['trail']:
            trail_x = px(BORDER + (ARROW_W + ARROW_GAP if is_left else 0))
            out.append(f'<text x="{trail_x}" y="{baseline_y:.1f}" '
                       f'font-size="{fs:.1f}" fill="#E8D5A3">{xe(ln["trail"])}</text>')

        # Distance — right-justified before right arrow, or at right edge
        if ln['distance']:
            if ln['arrow'] == 'right':
                dist_rx = (right_edge - ARROW_W - DIST_ARR_GAP) * PPI
            elif ln['arrow'] and not is_left:
                dist_rx = (right_edge - ARROW_W - ARROW_GAP) * PPI
            else:
                dist_rx = right_edge * PPI
            out.append(f'<text x="{dist_rx:.1f}" y="{baseline_y:.1f}" '
                       f'font-size="{fs:.1f}" fill="#E8D5A3" text-anchor="end">'
                       f'{xe(ln["distance"])}</text>')

    # Mounting holes
    for h in holes:
        cx, cy = h['x'] * PPI, h['y'] * PPI
        r  = (HOLE_DIA  / 2) * PPI
        rc = (CSINK_DIA / 2) * PPI
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rc:.1f}" '
                   f'fill="none" stroke="#E8D5A3" stroke-width="1" stroke-dasharray="4,2"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                   f'fill="#4A3520" stroke="#E8D5A3" stroke-width="1"/>')
        if h.get('slot'):
            slot_half = 0.4375 * PPI  # 7/16" half-length
            out.append(f'<rect x="{cx-slot_half:.1f}" y="{cy-rc:.1f}" '
                       f'width="{2*slot_half:.1f}" height="{2*rc:.1f}" '
                       f'rx="{rc:.1f}" fill="none" stroke="#E8D5A3" '
                       f'stroke-width="1" stroke-dasharray="4,2"/>')

    # Dimension label (below sign background, inside expanded viewport)
    out.append(f'<text x="{W/2:.0f}" y="{H+20:.0f}" font-size="14" '
               f'fill="#333" text-anchor="middle" font-weight="normal" '
               f'font-family="Arial" font-style="normal">'
               f'{sign_w:.3f}&quot; W x {sign_h:.3f}&quot; H</text>')

    out.append('</svg>')
    return '\n'.join(out)

def _svg_arrow(direction, x, y, w, h, color):
    """Return SVG polygon for an arrow."""
    hw = w * 0.4   # shaft half-width
    hx = x + w/2
    hy = y + h/2

    if direction == 'right':
        pts = [(x, y+h*0.3),(x+w*0.5,y+h*0.3),(x+w*0.5,y),
               (x+w,y+h*0.5),(x+w*0.5,y+h),(x+w*0.5,y+h*0.7),(x,y+h*0.7)]
    elif direction == 'left':
        pts = [(x+w,y+h*0.3),(x+w*0.5,y+h*0.3),(x+w*0.5,y),
               (x,y+h*0.5),(x+w*0.5,y+h),(x+w*0.5,y+h*0.7),(x+w,y+h*0.7)]
    elif direction == 'up':
        pts = [(hx,y),(x+w,y+h*0.5),(hx+hw/2,y+h*0.5),
               (hx+hw/2,y+h),(hx-hw/2,y+h),(hx-hw/2,y+h*0.5),(x,y+h*0.5)]
    else:  # down
        pts = [(hx,y+h),(x+w,y+h*0.5),(hx+hw/2,y+h*0.5),
               (hx+hw/2,y),(hx-hw/2,y),(hx-hw/2,y+h*0.5),(x,y+h*0.5)]

    ps = ' '.join(f'{px:.2f},{py:.2f}' for px, py in pts)
    return f'<polygon points="{ps}" fill="{color}"/>'

# ── DXF (ezdxf) ──────────────────────────────────────────────────────────────
def generate_dxf(sign_w, sign_h, positioned, content_w, holes, out_path):
    import ezdxf
    from ezdxf import colors

    doc = ezdxf.new('R2010')
    doc.header['$INSUNITS'] = 1  # inches
    msp = doc.modelspace()

    # Text style — references Highway Gothic Narrow Bold when installed on the CNC machine
    doc.styles.add('HGNB', font='HighwayGothicNarrow Bold.ttf')

    # Layers
    doc.layers.add('SIGN_OUTLINE', color=7)     # white
    doc.layers.add('TEXT_VCARVE',  color=1)     # red — v-carve text
    doc.layers.add('HOLES',        color=3)     # green — drill
    doc.layers.add('COUNTERSINK',  color=4)     # cyan — countersink
    doc.layers.add('ARROWS',       color=2)     # yellow

    # DXF Y origin is at bottom-left; flip: dxf_y = sign_h - svg_y
    def fy(y): return sign_h - y

    # Sign outline
    pts = [(0,0),(sign_w,0),(sign_w,sign_h),(0,sign_h)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={'layer':'SIGN_OUTLINE'})

    right_edge = BORDER + content_w

    for ln, y_top in positioned:
        baseline_y = fy(y_top + LETTER_H * 0.82)

        is_left = ln['arrow'] == 'left'
        trail_x = BORDER + (ARROW_W + ARROW_GAP if is_left else 0)

        # Trail name — MTEXT, left-aligned
        if ln['trail']:
            mt = msp.add_mtext(ln['trail'], dxfattribs={
                'layer': 'TEXT_VCARVE',
                'char_height': LETTER_H,
                'style': 'HGNB',
                'attachment_point': 4,  # middle-left
            })
            mt.set_location((trail_x, baseline_y))

        # Distance — MTEXT, right-aligned
        if ln['distance']:
            if ln['arrow'] == 'right':
                dist_rx = right_edge - ARROW_W - DIST_ARR_GAP
            elif ln['arrow'] and not is_left:
                dist_rx = right_edge - ARROW_W - ARROW_GAP
            else:
                dist_rx = right_edge

            mt = msp.add_mtext(ln['distance'], dxfattribs={
                'layer': 'TEXT_VCARVE',
                'char_height': LETTER_H,
                'style': 'HGNB',
                'attachment_point': 6,  # middle-right
            })
            mt.set_location((dist_rx, baseline_y))

        # Arrow geometry
        if ln['arrow']:
            ax  = BORDER if is_left else right_edge - ARROW_W
            ayb = fy(y_top + LETTER_H)
            _dxf_arrow(msp, ln['arrow'], ax, ayb, ARROW_W, LETTER_H)

    # Mounting holes
    for h in holes:
        hx, hy = h['x'], fy(h['y'])
        msp.add_circle((hx, hy), HOLE_DIA/2,  dxfattribs={'layer':'HOLES'})
        msp.add_circle((hx, hy), CSINK_DIA/2, dxfattribs={'layer':'COUNTERSINK'})
        if h.get('slot'):
            # Elongated slot as two circles + rectangle (simplified as ellipse ref)
            sl = 0.4375  # slot half-length
            # Draw as rounded rect via 4-point arc approximation — simplify to 2 circles + rect
            msp.add_circle((hx - sl, hy), CSINK_DIA/2, dxfattribs={'layer':'COUNTERSINK'})
            msp.add_circle((hx + sl, hy), CSINK_DIA/2, dxfattribs={'layer':'COUNTERSINK'})
            # Rect sides
            msp.add_line((hx-sl, hy-CSINK_DIA/2), (hx+sl, hy-CSINK_DIA/2),
                         dxfattribs={'layer':'COUNTERSINK'})
            msp.add_line((hx-sl, hy+CSINK_DIA/2), (hx+sl, hy+CSINK_DIA/2),
                         dxfattribs={'layer':'COUNTERSINK'})

    doc.saveas(out_path)

def _dxf_arrow(msp, direction, x, y_bottom, w, h):
    """Add closed arrow polyline to DXF modelspace."""
    hw = w * 0.4
    hx = x + w/2

    if direction == 'right':
        verts = [
            (x,        y_bottom+h*0.3),
            (x+w*0.5,  y_bottom+h*0.3),
            (x+w*0.5,  y_bottom),
            (x+w,      y_bottom+h*0.5),
            (x+w*0.5,  y_bottom+h),
            (x+w*0.5,  y_bottom+h*0.7),
            (x,        y_bottom+h*0.7),
        ]
    elif direction == 'left':
        verts = [
            (x+w,      y_bottom+h*0.3),
            (x+w*0.5,  y_bottom+h*0.3),
            (x+w*0.5,  y_bottom),
            (x,        y_bottom+h*0.5),
            (x+w*0.5,  y_bottom+h),
            (x+w*0.5,  y_bottom+h*0.7),
            (x+w,      y_bottom+h*0.7),
        ]
    elif direction == 'up':
        verts = [
            (hx,       y_bottom+h),
            (x+w,      y_bottom+h*0.5),
            (hx+hw/2,  y_bottom+h*0.5),
            (hx+hw/2,  y_bottom),
            (hx-hw/2,  y_bottom),
            (hx-hw/2,  y_bottom+h*0.5),
            (x,        y_bottom+h*0.5),
        ]
    else:  # down
        verts = [
            (hx,       y_bottom),
            (x+w,      y_bottom+h*0.5),
            (hx+hw/2,  y_bottom+h*0.5),
            (hx+hw/2,  y_bottom+h),
            (hx-hw/2,  y_bottom+h),
            (hx-hw/2,  y_bottom+h*0.5),
            (x,        y_bottom+h*0.5),
        ]

    msp.add_lwpolyline(verts, close=True, dxfattribs={'layer':'ARROWS'})

# ── CRV template patching ────────────────────────────────────────────────────
def _crv_find_stream_sectors(raw, stream_name_fragment):
    """Return (sector_ids, stream_size, dir_size_offset) for an OLE2 stream."""
    import struct
    assert raw[:8] == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1', "Not an OLE2 file"
    SS = 512

    # Build FAT from DIFAT table in header
    difat = struct.unpack_from('<109I', raw, 76)
    fat = []
    for sid in difat:
        if sid >= 0xFFFFFFFC:
            break
        off = (sid + 1) * SS
        fat.extend(struct.unpack_from(f'<{SS//4}I', raw, off))

    # Walk directory
    first_dir = struct.unpack_from('<I', raw, 48)[0]
    dir_sectors = []
    s = first_dir
    while s < 0xFFFFFFFC:
        dir_sectors.append(s)
        s = fat[s]

    # Search directory entries for our stream
    frag = stream_name_fragment.encode('utf-16-le')
    for ds in dir_sectors:
        base = (ds + 1) * SS
        for i in range(4):
            off = base + i * 128
            entry = raw[off:off+128]
            name_len = struct.unpack_from('<H', entry, 64)[0]
            if name_len < 2:
                continue
            name_bytes = entry[:name_len-2]
            if frag in name_bytes:
                start = struct.unpack_from('<I', entry, 116)[0]
                size  = struct.unpack_from('<I', entry, 120)[0]
                dir_size_off = off + 120
                # Follow FAT chain
                sectors = []
                sec = start
                while sec < 0xFFFFFFFC:
                    sectors.append(sec)
                    sec = fat[sec] if sec < len(fat) else 0xFFFFFFFE
                return sectors, size, dir_size_off

    raise ValueError(f"Stream '{stream_name_fragment}' not found in OLE2 file")


def patch_crv(template_path, output_path, replacements):
    """
    Copy template .crv and replace _txtAL_Text values in order.
    replacements: list of (old_text, new_text) strings.
    """
    import struct

    with open(template_path, 'rb') as f:
        raw = bytearray(f.read())

    sectors, stream_size, dir_size_off = _crv_find_stream_sectors(raw, '2dDataV2')
    SS = 512
    allocated = len(sectors) * SS

    # Read stream data from raw file
    stream = bytearray()
    for sid in sectors:
        stream.extend(raw[(sid+1)*SS : (sid+1)*SS + SS])
    stream = stream[:stream_size]

    # Apply replacements in order — find each _txtAL_Text occurrence sequentially
    needle = '_txtAL_Text'.encode('utf-16-le')
    search_from = 0
    rep_idx = 0

    while rep_idx < len(replacements):
        old_text, new_text = replacements[rep_idx]
        idx = stream.find(needle, search_from)
        if idx < 0:
            print(f'Warning: ran out of _txtAL_Text fields (needed {len(replacements)}, found {rep_idx})')
            break
        after = idx + len(needle)
        if stream[after:after+7] != b'\x03\x00\x00\x00\xff\xfe\xff':
            search_from = idx + 2
            continue  # skip non-string fields

        old_len = stream[after+7]
        old_utf16 = stream[after+8 : after+8+old_len*2]
        found_text = old_utf16.decode('utf-16-le')

        new_utf16 = new_text.encode('utf-16-le')
        new_len = len(new_text)
        assert new_len <= 255, f"Text too long (max 255 chars): {new_text}"

        # Build replacement bytes for the value (keep field name)
        new_value = b'\x03\x00\x00\x00\xff\xfe\xff' + bytes([new_len]) + new_utf16
        old_value = b'\x03\x00\x00\x00\xff\xfe\xff' + bytes([old_len]) + bytes(old_utf16)

        stream[after:after+len(old_value)] = new_value
        # Adjust if lengths differ
        delta = len(new_value) - len(old_value)
        if delta != 0:
            # new_value was already spliced; nothing extra needed since bytearray handles it
            pass

        print(f'  [{rep_idx+1}] "{found_text}" → "{new_text}"')
        search_from = after + len(new_value)
        rep_idx += 1

    # Verify it fits
    if len(stream) > allocated:
        raise ValueError(
            f"Modified stream ({len(stream)} bytes) exceeds allocated space "
            f"({allocated} bytes). Choose a template with longer original text."
        )

    # Write stream back to sectors (pad last sector with zeros)
    padded = stream + bytearray(allocated - len(stream))
    for i, sid in enumerate(sectors):
        off = (sid+1) * SS
        raw[off:off+SS] = padded[i*SS:(i+1)*SS]

    # Update stream size in directory entry
    struct.pack_into('<I', raw, dir_size_off, len(stream))

    with open(output_path, 'wb') as f:
        f.write(raw)
    print(f'CRV written → {output_path}')


# ── Main ──────────────────────────────────────────────────────────────────────
def main(sign_text=None):
    if sign_text is None:
        sign_text = 'SWAMPY LOOP//SWAMPY SNOW PARK 1 1/2 >//SWAMPY SHELTER  1/2 ^'

    # Optional filename prefix: "myfile: sign text..."
    base_name = 'forest_service_sign'
    m = re.match(r'^([^/:]+):\s*', sign_text)
    if m:
        base_name = m.group(1).strip()
        sign_text = sign_text[m.end():]

    print(f'Input: {sign_text}\n')
    lines = parse_sign(sign_text)

    print('Parsed lines:')
    for i, ln in enumerate(lines):
        print(f'  {i+1}: trail="{ln["trail"]}"  dist="{ln["distance"]}"  '
              f'arrow="{ln["arrow"]}"  continuation={ln["is_continuation"]}')

    sign_w, sign_h, positioned, content_w = layout(lines)
    print(f'\nSign size: {sign_w:.3f}" W  ×  {sign_h:.3f}" H')

    holes = hole_positions(sign_w, sign_h)
    print(f'Mounting holes: {len(holes)} '
          f'({"elongated top" if sign_h > TALL_SIGN_THRESH else "round"})')

    # SVG
    svg = generate_svg(sign_w, sign_h, positioned, content_w, holes)
    svg_path = f'{base_name}.svg'
    with open(svg_path, 'w') as f:
        f.write(svg)
    print(f'\nSVG preview  → {svg_path}')

    # DXF
    dxf_path = f'{base_name}.dxf'
    generate_dxf(sign_w, sign_h, positioned, content_w, holes, dxf_path)
    print(f'VCarve DXF   → {dxf_path}')

    print('\nDXF Layers:')
    print('  SIGN_OUTLINE  — sign boundary (profile cut)')
    print('  TEXT_VCARVE   — text entities (select Highway Gothic Narrow Bold in VCarve)')
    print('  ARROWS        — arrow geometry (v-carve at same depth as text)')
    print('  HOLES         — 3/8" drill holes  depth .25"')
    print('  COUNTERSINK   — 3/4" countersink  depth .13"')

def main_crv(template_path, sign_text, base_name):
    """Patch a .crv template with new sign text."""
    lines = parse_sign(sign_text)
    print('Parsed lines:')
    for i, ln in enumerate(lines):
        print(f'  {i+1}: trail="{ln["trail"]}"  dist="{ln["distance"]}"  arrow="{ln["arrow"]}"')

    # Build ordered list of (trail_name, distance) per non-continuation line
    # matching the order text objects appear in the .crv: trail1, trail2... then distances
    trail_texts = [ln['trail'] for ln in lines if ln['trail']]
    dist_texts  = [ln['distance'] for ln in lines if ln['distance']]

    # Read current values from template to build replacements
    import olefile
    ole = olefile.OleFileIO(template_path)
    data = ole.openstream('VectorData/2dDataV2').read()
    ole.close()

    needle = '_txtAL_Text'.encode('utf-16-le')
    template_texts = []
    pos = 0
    while True:
        idx = data.find(needle, pos)
        if idx < 0: break
        after = idx + len(needle)
        if data[after:after+7] == b'\x03\x00\x00\x00\xff\xfe\xff':
            slen = data[after+7]
            val = data[after+8:after+8+slen*2].decode('utf-16-le')
            template_texts.append(val)
        pos = idx + 2

    new_texts = trail_texts + dist_texts
    if len(new_texts) != len(template_texts):
        print(f'Warning: template has {len(template_texts)} text objects, '
              f'sign has {len(new_texts)}. Counts must match.')
        print(f'  Template: {template_texts}')
        print(f'  New:      {new_texts}')
        return

    replacements = list(zip(template_texts, new_texts))
    out_path = f'{base_name}.crv'
    patch_crv(template_path, out_path, replacements)

    # Also generate SVG preview
    sign_w, sign_h, positioned, content_w = layout(lines)
    holes = hole_positions(sign_w, sign_h)
    svg = generate_svg(sign_w, sign_h, positioned, content_w, holes)
    svg_path = f'{base_name}.svg'
    with open(svg_path, 'w') as f:
        f.write(svg)
    print(f'SVG preview  → {svg_path}')
    print(f'Sign size: {sign_w:.3f}" W x {sign_h:.3f}" H')


if __name__ == '__main__':
    args = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else None

    # Check for --template flag: --template path.crv "sign text"
    if args and '--template' in args:
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument('--template', required=True)
        p.add_argument('sign_text', nargs=argparse.REMAINDER)
        parsed = p.parse_args()
        sign_text = ' '.join(parsed.sign_text).strip()

        base_name = 'output_sign'
        m = re.match(r'^([^/:]+):\s*', sign_text)
        if m:
            base_name = m.group(1).strip()
            sign_text = sign_text[m.end():]

        main_crv(parsed.template, sign_text, base_name)
    else:
        main(args)
