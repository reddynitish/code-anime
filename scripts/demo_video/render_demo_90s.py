import os
import sys
import math
import subprocess
import json
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# -----------------------------------------------------------------------------
# VIDEO SPECIFICATIONS & TIMING
# -----------------------------------------------------------------------------
WIDTH = 1920
HEIGHT = 1080
FPS = 30
TOTAL_DURATION = 90.0
TOTAL_FRAMES = int(FPS * TOTAL_DURATION) # Exactly 2700 frames

# Editorial act transitions snapped to audio cues (AD_AUDIO_READY.md)
T_ACT1_END = 14.66   # Snap cue
T_ACT2_END = 25.00   # Impact cue
T_ACT3_END = 46.14   # Boom cue (biggest pre-climax hit)
T_ACT4_END = 60.80   # Lead-in into full 10s prototype video
T_ACT5_END = 70.80   # Exact end of 10s prototype video
T_ACT6_END = 83.19   # Snap_boom cue

# -----------------------------------------------------------------------------
# PALETTE (Warm cinematic cream, coral, rich navy, cyan, mint, gold)
# -----------------------------------------------------------------------------
BG_DARK = (10, 14, 23, 255)           # Deep cinematic navy #0a0e17
TEXT_CREAM = (248, 245, 237, 255)     # Editorial warm cream #f8f5ed
TEXT_MUTED = (168, 178, 196, 255)     # Soft slate #a8b2c4
TEXT_SUBTLE = (105, 117, 138, 255)    # Subtle slate
ACCENT_CORAL = (255, 107, 74, 255)    # Hero coral #ff6b4a
ACCENT_CYAN = (56, 189, 248, 255)     # Wan cyan
ACCENT_MINT = (52, 211, 153, 255)     # Review mint
ACCENT_GOLD = (251, 191, 36, 255)     # Highlight gold
PILL_BG = (12, 18, 30, 200)           # Glass dark pill
BORDER_SUBTLE = (255, 255, 255, 30)

# Fonts
FONT_ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_HELVETICA = "/System/Library/Fonts/HelveticaNeue.ttc"

def get_font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_ARIAL, size)
    except Exception:
        try:
            return ImageFont.truetype(FONT_HELVETICA, size)
        except Exception:
            return ImageFont.load_default()

FONT_HERO = get_font(72, bold=True)
FONT_HEADLINE = get_font(54, bold=True)
FONT_BIG_IMPACT = get_font(108, bold=True)
FONT_TITLE = get_font(38, bold=True)
FONT_SUBTITLE = get_font(26, bold=False)
FONT_BODY = get_font(22, bold=False)
FONT_TAG = get_font(16, bold=True)
FONT_BIG_NUM = get_font(96, bold=True)

# -----------------------------------------------------------------------------
# PRE-COMPUTED FULL-WIDTH SMOOTH GRADIENT SCRIM MASK
# -----------------------------------------------------------------------------
SCRIM_HEIGHT = 440
PRECOMP_SCRIM = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
s_draw = ImageDraw.Draw(PRECOMP_SCRIM)
for i in range(SCRIM_HEIGHT):
    ratio = i / float(SCRIM_HEIGHT)
    alpha = int(240 * (ratio ** 1.8))
    y = HEIGHT - SCRIM_HEIGHT + i
    s_draw.line([(0, y), (WIDTH, y)], fill=(8, 12, 20, alpha))

# -----------------------------------------------------------------------------
# ASSET CACHING & FAST NORMALIZATION
# -----------------------------------------------------------------------------
ASSET_CACHE = {}

def get_image(path, target_max_dim=1920):
    if path in ASSET_CACHE:
        return ASSET_CACHE[path]
    if not os.path.exists(path):
        return None
    try:
        im = Image.open(path).convert("RGBA")
        if max(im.size) > target_max_dim:
            ratio = target_max_dim / float(max(im.size))
            new_size = (int(im.width * ratio), int(im.height * ratio))
            im = im.resize(new_size, Image.Resampling.BILINEAR)
        ASSET_CACHE[path] = im
        return im
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

# Load genuine 10s Wan prototype frames (160 frames at 16fps)
WAN_10S_DIR = "output/demo90/wan_10s_frames"
WAN_FRAMES = []

def init_wan_frames():
    global WAN_FRAMES
    if not os.path.exists(WAN_10S_DIR) or len(os.listdir(WAN_10S_DIR)) < 160:
        os.makedirs(WAN_10S_DIR, exist_ok=True)
        print("Extracting wan 10s frames via ffmpeg...")
        subprocess.run([
            "ffmpeg", "-y", "-i", "output/wan_final/final_10s.mp4",
            os.path.join(WAN_10S_DIR, "f_%04d.png")
        ], check=True)
    
    files = sorted([os.path.join(WAN_10S_DIR, f) for f in os.listdir(WAN_10S_DIR) if f.startswith("f_") and f.endswith(".png")])
    for f in files:
        WAN_FRAMES.append(Image.open(f).convert("RGBA"))
    print(f"Loaded {len(WAN_FRAMES)} genuine Wan 10s frames from {WAN_10S_DIR}")

init_wan_frames()

KEYFRAME_DIR = "output/keyframes/production_batch_v1"

# -----------------------------------------------------------------------------
# GRAPHICS & ANIMATION UTILITIES
# -----------------------------------------------------------------------------
def ease_in_out(t):
    return 0.5 * (1.0 - math.cos(math.pi * t))

def ease_out(t):
    return math.sin(t * (math.pi / 2.0))

def render_cinematic_crop(src_img, target_w, target_h, scale, pan_x=0.0, pan_y=0.0):
    if src_img is None:
        return Image.new("RGBA", (target_w, target_h), BG_DARK)
    
    base_scale = max(target_w / float(src_img.width), target_h / float(src_img.height)) * scale
    nw = int(src_img.width * base_scale)
    nh = int(src_img.height * base_scale)
    
    scaled = src_img.resize((nw, nh), Image.Resampling.BILINEAR)
    
    center_x = (nw - target_w) / 2.0 + pan_x * ((nw - target_w) / 2.0)
    center_y = (nh - target_h) / 2.0 + pan_y * ((nh - target_h) / 2.0)
    
    left = max(0, min(nw - target_w, int(center_x)))
    top = max(0, min(nh - target_h, int(center_y)))
    
    return scaled.crop((left, top, left + target_w, top + target_h))

def apply_bottom_scrim(base_img):
    return Image.alpha_composite(base_img, PRECOMP_SCRIM)

def draw_tiny_brand(draw):
    """Clean minimal brand mark in top corner. NO act chrome, timecode, or progress bars."""
    draw.text((80, 48), "code-anime", fill=TEXT_CREAM, font=FONT_TAG)
    draw.text((185, 48), "•", fill=ACCENT_CORAL, font=FONT_TAG)
    draw.text((200, 48), "STUDIO WORKFLOW", fill=TEXT_MUTED, font=FONT_TAG)

def draw_pill_badge(draw, text, xy, bg_color=PILL_BG, border_color=ACCENT_CORAL, text_color=TEXT_CREAM, font=FONT_TAG):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    px, py = 14, 7
    rect = (xy[0], xy[1], xy[0] + tw + px*2, xy[1] + th + py*2)
    draw.rounded_rectangle(rect, radius=6, fill=bg_color, outline=border_color, width=1)
    draw.text((xy[0] + px, xy[1] + py - 1), text, fill=text_color, font=font)
    return rect

def draw_vector_arrow(draw, x1, y, x2, color=ACCENT_GOLD, width=3):
    draw.line([(x1, y), (x2, y)], fill=color, width=width)
    ah = 7
    draw.polygon([(x2, y - ah), (x2 + 12, y), (x2, y + ah)], fill=color)

# -----------------------------------------------------------------------------
# TRANSITION EFFECTS: Flash snaps and blurred directional wipes
# -----------------------------------------------------------------------------
CUT_CUES = [
    0.25, 4.5, 9.0, 14.66, 18.0, 21.3, 25.0, 27.2, 29.6, 32.0, 34.5, 37.0, 39.5, 42.0,
    46.14, 50.0, 54.0, 58.0, 60.80, 70.80, 75.0, 79.2, 83.19
]

def apply_editorial_transitions(img, t):
    """
    Subtle 50-150ms snap flash or subtle vignette blur right at editorial cuts.
    High impact without nausea.
    """
    for cue in CUT_CUES:
        diff = t - cue
        if 0.0 <= diff <= 0.12:  # 0 to 120ms snap flash
            flash_intensity = int(140 * (1.0 - (diff / 0.12)))
            flash_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, flash_intensity))
            return Image.alpha_composite(img, flash_overlay)
    return img

# -----------------------------------------------------------------------------
# ACT 1: THE SOLO STORYTELLER'S DILEMMA (0.0s - 14.66s)
# -----------------------------------------------------------------------------
def render_act1(fidx, t):
    ref_img = get_image("assets/references/ref3_latest_male_night.png")
    
    if t < 4.5:
        sub_t = t / 4.5
        scale = 1.90 + 0.20 * ease_in_out(sub_t)
        bg = render_cinematic_crop(ref_img, WIDTH, HEIGHT, scale, pan_x=0.06, pan_y=0.06)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        # 2-4s short caption reveal with translate/opacity
        reveal = min(1.0, (t - 0.2) / 0.6) if t >= 0.2 else 0.0
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "CONCEPT SEED", (100, HEIGHT - 230 + y_off), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
        draw.text((100, HEIGHT - 175 + y_off), "Imagine An Entire World.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Every world starts in the mind of a single creator.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    elif t < 9.0:
        sub_t = (t - 4.5) / 4.5
        scale = 1.55 - 0.45 * ease_out(sub_t)
        bg = render_cinematic_crop(ref_img, WIDTH, HEIGHT, scale, pan_x=0.0, pan_y=0.0)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 4.7) / 0.6) if t >= 4.7 else 0.0
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "THE VISION", (100, HEIGHT - 230 + y_off), border_color=ACCENT_CYAN, text_color=ACCENT_CYAN)
        draw.text((100, HEIGHT - 175 + y_off), "The Quiet Room Awakens.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "The characters. The tension. The start of an adventure.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    else:
        sub_t = (t - 9.0) / (T_ACT1_END - 9.0)
        scale = 1.05 + 0.12 * ease_in_out(sub_t)
        bg = render_cinematic_crop(ref_img, WIDTH, HEIGHT, scale, pan_x=-0.10, pan_y=0.05)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 9.2) / 0.6) if t >= 9.2 else 0.0
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "THE CHALLENGE", (100, HEIGHT - 230 + y_off), border_color=ACCENT_GOLD, text_color=ACCENT_GOLD)
        draw.text((100, HEIGHT - 175 + y_off), "Animation Takes A Whole Studio.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Turning that vision into motion was out of reach.", fill=TEXT_MUTED, font=FONT_SUBTITLE)

    return img

# -----------------------------------------------------------------------------
# ACT 2: ENTER CODE-ANIME (14.66s - 25.00s)
# Layout breaker: Black bold typography intermission ("One Storyteller.")
# -----------------------------------------------------------------------------
def render_act2(fidx, t):
    # 14.66 to 16.5: Clean bold typography card on deep black to break constant layout
    if t < 16.60:
        img = Image.new("RGBA", (WIDTH, HEIGHT), BG_DARK)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        sub_t = (t - T_ACT1_END) / (16.60 - T_ACT1_END)
        reveal = min(1.0, sub_t / 0.4)
        y_off = int((1.0 - reveal) * 20)
        
        draw_pill_badge(draw, "ENTER CODE-ANIME", (WIDTH//2 - 110, 360 + y_off), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
        
        main_title = "One Storyteller."
        tbbox = FONT_BIG_IMPACT.getbbox(main_title)
        tw = tbbox[2] - tbbox[0]
        draw.text(((WIDTH - tw)//2, 440 + y_off), main_title, fill=TEXT_CREAM, font=FONT_BIG_IMPACT)
        
        sub_text = "A production workflow built for solo creators."
        sbbox = FONT_TITLE.getbbox(sub_text)
        sw = sbbox[2] - sbbox[0]
        draw.text(((WIDTH - sw)//2, 580 + y_off), sub_text, fill=ACCENT_CYAN, font=FONT_TITLE)
        return img
        
    elif t < 19.50:
        sub_t = (t - 16.60) / (19.50 - 16.60)
        ref_img = get_image("assets/references/ref3_latest_male_night.png")
        scale = 1.10 + 0.10 * ease_in_out(sub_t)
        bg = render_cinematic_crop(ref_img, WIDTH, HEIGHT, scale, pan_x=-0.05, pan_y=0.0)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 16.8) / 0.5)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "INPUT // STEP 01", (100, HEIGHT - 230 + y_off), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
        draw.text((100, HEIGHT - 175 + y_off), "Bring A Reference Image.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "One concept art piece establishes your world and character.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        return img
        
    elif t < 22.30:
        sub_t = (t - 19.50) / (22.30 - 19.50)
        room_img = get_image("output/keyframes/production_batch_v1/bg_clean_plate_room_00.png")
        scale = 1.05 + 0.12 * ease_in_out(sub_t)
        bg = render_cinematic_crop(room_img, WIDTH, HEIGHT, scale, pan_x=0.05, pan_y=-0.05)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 19.7) / 0.5)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "DIRECT // STEP 02", (100, HEIGHT - 230 + y_off), border_color=ACCENT_CYAN, text_color=ACCENT_CYAN)
        draw.text((100, HEIGHT - 175 + y_off), "Describe The Scene.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Direct action in plain natural language without 3D rigging.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        return img
        
    else:
        # Layout breaker: Black bold typography intermission ("Focus On Story.")
        img = Image.new("RGBA", (WIDTH, HEIGHT), BG_DARK)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        sub_t = (t - 22.30) / (T_ACT2_END - 22.30)
        reveal = min(1.0, sub_t / 0.4)
        y_off = int((1.0 - reveal) * 20)
        
        draw_pill_badge(draw, "GENERATE // STEP 03", (WIDTH//2 - 120, 360 + y_off), border_color=ACCENT_MINT, text_color=ACCENT_MINT)
        
        main_title = "Focus On The Story."
        tbbox = FONT_BIG_IMPACT.getbbox(main_title)
        tw = tbbox[2] - tbbox[0]
        draw.text(((WIDTH - tw)//2, 440 + y_off), main_title, fill=TEXT_CREAM, font=FONT_BIG_IMPACT)
        
        sub_text = "code-anime coordinates asset expansion, motion, and assembly."
        sbbox = FONT_TITLE.getbbox(sub_text)
        sw = sbbox[2] - sbbox[0]
        draw.text(((WIDTH - sw)//2, 580 + y_off), sub_text, fill=ACCENT_CORAL, font=FONT_TITLE)
        return img

# -----------------------------------------------------------------------------
# ACT 3: ARCHITECTURE & ASSET MONTAGE (25.00s - 46.14s)
# -----------------------------------------------------------------------------
def render_act3(fidx, t):
    montage_cuts = [
        (25.00, 27.50, "char_turn_front_00.png", "FRONT TURNAROUND", "LUMINAL SEED", 0),
        (27.50, 30.00, "char_turn_three_quarter_r_00.png", "3/4 ANGLE MODEL", "CHARACTER MODEL", 0),
        (30.00, 32.50, "char_turn_profile_l_00.png", "PROFILE TURNAROUND", "TURNAROUND SHEET", 0),
        (32.50, 35.00, "bed_edge_hand_plant_00.png", "BED CONTACT ANCHOR", "WAN 2.1 MOTION", 1),
        (35.00, 37.80, "wan_ctrl_wake_sit_00.png", "SEATED POSE ANCHOR", "POSE CONTINUITY", 1),
        (37.80, 40.50, "feet_bare_floor_step_00.png", "FLOOR STRIDE ANCHOR", "STRIDE CONTINUITY", 1),
        (40.50, 43.20, "hand_handle_approach_00.png", "DOORWAY INTERACTION", "LOCAL REVIEW", 2),
        (43.20, T_ACT3_END, "door_hallway_spill_90deg_00.png", "LIGHT SPILL FINALE", "ASSEMBLY QUEUE", 2),
    ]
    
    current_cut = montage_cuts[-1]
    for cut in montage_cuts:
        if cut[0] <= t < cut[1]:
            current_cut = cut
            break
            
    c_start, c_end, fname, label, badge, active_flow_stage = current_cut
    cut_duration = c_end - c_start
    sub_t = (t - c_start) / max(0.01, cut_duration)
    
    scale = 1.08 + 0.12 * ease_in_out(sub_t)
    pan_x = 0.05 * math.sin(sub_t * math.pi)
    pan_y = -0.04 * math.sin(sub_t * math.pi)
    
    asset_img = get_image(os.path.join(KEYFRAME_DIR, fname))
    bg = render_cinematic_crop(asset_img, WIDTH, HEIGHT, scale, pan_x, pan_y)
    img = apply_bottom_scrim(bg)
    draw = ImageDraw.Draw(img)
    draw_tiny_brand(draw)
    
    # PURPOSEFUL FLOW GRAPHIC: Luminal -> Wan / Kaggle -> Review
    flow_y = 100
    stages = [
        ("01 Luminal", "Keyframe Assets", ACCENT_CORAL),
        ("02 Wan / Kaggle", "Open-Weight Motion", ACCENT_CYAN),
        ("03 Local Review", "Shot Assembly", ACCENT_MINT)
    ]
    
    box_w = 340
    box_h = 60
    total_flow_w = 3 * box_w + 2 * 60
    start_fx = (WIDTH - total_flow_w) // 2
    
    for i, (stitle, ssub, scol) in enumerate(stages):
        bx = start_fx + i * (box_w + 60)
        is_active = (i == active_flow_stage)
        
        bg_fill = (14, 22, 38, 230) if is_active else (10, 15, 26, 170)
        border_col = scol if is_active else (255, 255, 255, 30)
        b_width = 2 if is_active else 1
        
        draw.rounded_rectangle((bx, flow_y, bx + box_w, flow_y + box_h), radius=10, fill=bg_fill, outline=border_col, width=b_width)
        draw.text((bx + 20, flow_y + 12), stitle, fill=scol if is_active else TEXT_CREAM, font=FONT_TAG)
        draw.text((bx + 20, flow_y + 34), ssub, fill=TEXT_CREAM if is_active else TEXT_MUTED, font=FONT_BODY)
        
        if i < 2:
            ax1 = bx + box_w + 14
            ax2 = bx + box_w + 42
            draw_vector_arrow(draw, ax1, flow_y + 30, ax2, color=ACCENT_GOLD if (is_active or i==0 and active_flow_stage>0) else (148, 163, 184, 150))
            
    reveal = min(1.0, (t - c_start) / 0.4)
    y_off = int((1.0 - reveal) * 16)
    
    draw_pill_badge(draw, badge, (100, HEIGHT - 230 + y_off), border_color=ACCENT_CYAN, text_color=ACCENT_CYAN)
    
    if active_flow_stage == 0:
        headline = "Luminal Generates Reusable Assets."
        subline = "Turnaround references and keyframes ground character identity."
    elif active_flow_stage == 1:
        headline = "Wan Models Render Motion On Kaggle."
        subline = "Open weights power real generative video without paid infrastructure."
    else:
        headline = "Local Review Verifies Continuity."
        subline = "Automated frame checks and cut assembly polish every individual beat."
        
    draw.text((100, HEIGHT - 175 + y_off), headline, fill=TEXT_CREAM, font=FONT_HERO)
    draw.text((100, HEIGHT - 90 + y_off), subline, fill=TEXT_MUTED, font=FONT_SUBTITLE)
    return img

# -----------------------------------------------------------------------------
# ACT 4: THE TEST BRIEF (46.14s - 60.80s)
# -----------------------------------------------------------------------------
def render_act4(fidx, t):
    if t < 50.0:
        sub_t = (t - T_ACT3_END) / (50.0 - T_ACT3_END)
        room_img = get_image("output/keyframes/production_batch_v1/bg_clean_plate_room_00.png")
        scale = 1.08 + 0.12 * ease_in_out(sub_t)
        bg = render_cinematic_crop(room_img, WIDTH, HEIGHT, scale, pan_x=0.0, pan_y=0.0)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - T_ACT3_END) / 0.5)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "TEST BRIEF SPECIFICATION", (100, HEIGHT - 240 + y_off), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
        draw_pill_badge(draw, "10-SECOND BENCHMARK", (430, HEIGHT - 240 + y_off), border_color=ACCENT_GOLD, text_color=ACCENT_GOLD)
        
        draw.text((100, HEIGHT - 175 + y_off), "One Character. Bedroom. Ten Seconds.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Three consecutive actions: Get out of bed. Walk to door. Open it.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    elif t < 53.6:
        sub_t = (t - 50.0) / 3.6
        bed_img = get_image("output/keyframes/production_batch_v1/wan_ctrl_bed_wake_00.png")
        scale = 1.10 + 0.10 * ease_in_out(sub_t)
        bg = render_cinematic_crop(bed_img, WIDTH, HEIGHT, scale, pan_x=-0.06, pan_y=0.06)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 50.0) / 0.4)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "ACTION 01 • RENDERED", (100, HEIGHT - 240 + y_off), border_color=ACCENT_MINT, text_color=ACCENT_MINT)
        draw.text((100, HEIGHT - 175 + y_off), "Stand. Get Out Of Bed.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Character shifts weight and rises from bedding. 160 frames verified.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    elif t < 57.2:
        sub_t = (t - 53.6) / 3.6
        walk_img = get_image("output/keyframes/production_batch_v1/wan_ctrl_walk_mid_00.png")
        scale = 1.08 + 0.12 * ease_in_out(sub_t)
        bg = render_cinematic_crop(walk_img, WIDTH, HEIGHT, scale, pan_x=0.05, pan_y=0.02)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 53.6) / 0.4)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "ACTION 02 • IN PROGRESS", (100, HEIGHT - 240 + y_off), border_color=ACCENT_GOLD, text_color=ACCENT_GOLD)
        draw.text((100, HEIGHT - 175 + y_off), "Walk. Stride Across Room.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Mid-stride keyframes prepared. Hand and step continuity being evaluated.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    else:
        sub_t = (t - 57.2) / (T_ACT4_END - 57.2)
        door_img = get_image("output/keyframes/production_batch_v1/door_swing_45deg_00.png")
        scale = 1.08 + 0.10 * ease_in_out(sub_t)
        bg = render_cinematic_crop(door_img, WIDTH, HEIGHT, scale, pan_x=-0.04, pan_y=-0.04)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 57.2) / 0.4)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "ACTION 03 • KEYFRAMED", (100, HEIGHT - 240 + y_off), border_color=ACCENT_CYAN, text_color=ACCENT_CYAN)
        draw.text((100, HEIGHT - 175 + y_off), "Open. Doorway Spill.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Latches door; hallway warm spill illuminates bedroom floor.", fill=TEXT_MUTED, font=FONT_SUBTITLE)

    return img

# -----------------------------------------------------------------------------
# ACT 5: REALTIME 10.0s PROTOTYPE FOOTAGE (60.80s - 70.80s)
# Embeds full 10s actual video ONCE in realtime (160 frames over 10s = 16fps upsampled to 30fps)
# No overlays obscuring center action. Small PROTOTYPE label truth of capabilities.
# -----------------------------------------------------------------------------
def render_act5(fidx, t):
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_DARK)
    
    # Timeline 60.80 to 70.80 = exactly 10.00 seconds
    clip_elapsed = t - T_ACT4_END # 0.0 to 10.0
    wan_idx = min(len(WAN_FRAMES) - 1, max(0, int(clip_elapsed * 16.0)))
    
    current_frame = WAN_FRAMES[wan_idx] if WAN_FRAMES else None
    
    # Center frame in full cinematic theater: 1600 x 923 (or aspect correct 832x480 -> 1664x960)
    vw = 1664
    vh = 960
    vx = (WIDTH - vw) // 2
    vy = (HEIGHT - vh) // 2
    
    if current_frame:
        scaled = current_frame.resize((vw, vh), Image.Resampling.BILINEAR)
        img.paste(scaled, (vx, vy))
        
    draw = ImageDraw.Draw(img)
    draw_tiny_brand(draw)
    
    # Outer thin border
    draw.rounded_rectangle((vx - 2, vy - 2, vx + vw + 2, vy + vh + 2), radius=10, outline=ACCENT_CORAL, width=2)
    
    # Non-obscuring top-left & bottom-right truthful corner labels
    draw_pill_badge(draw, "PROTOTYPE GENERATION // REALTIME 10s", (vx + 32, vy + 32), bg_color=(10, 14, 23, 210), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
    
    draw_pill_badge(draw, "MOTION NEEDS REFINEMENT • EVALUATION RUN", (vx + vw - 480, vy + vh - 56), bg_color=(10, 14, 23, 210), border_color=ACCENT_GOLD, text_color=ACCENT_GOLD)

    return img

# -----------------------------------------------------------------------------
# ACT 6: FUTURE ROADMAP (70.80s - 83.19s)
# -----------------------------------------------------------------------------
def render_act6(fidx, t):
    if t < 75.0:
        sub_t = (t - T_ACT5_END) / (75.0 - T_ACT5_END)
        char_img = get_image("output/keyframes/production_batch_v1/char_turn_front_00.png")
        scale = 1.08 + 0.14 * ease_in_out(sub_t)
        bg = render_cinematic_crop(char_img, WIDTH, HEIGHT, scale, pan_x=0.0, pan_y=0.05)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - T_ACT5_END) / 0.5)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "ROADMAP // IDENTITY", (100, HEIGHT - 240 + y_off), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
        draw.text((100, HEIGHT - 175 + y_off), "Reusable Characters.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Consistent facial identity, costume memory, and performance across every scene.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    elif t < 79.2:
        sub_t = (t - 75.0) / (79.2 - 75.0)
        hall_img = get_image("output/keyframes/production_batch_v1/door_hallway_spill_90deg_00.png")
        scale = 1.06 + 0.14 * ease_in_out(sub_t)
        bg = render_cinematic_crop(hall_img, WIDTH, HEIGHT, scale, pan_x=-0.05, pan_y=0.0)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 75.0) / 0.5)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "ROADMAP // CONTINUITY", (100, HEIGHT - 240 + y_off), border_color=ACCENT_CYAN, text_color=ACCENT_CYAN)
        draw.text((100, HEIGHT - 175 + y_off), "Longer Scenes.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "Multi-shot narrative arcs, spatial consistency, and native soundscapes.", fill=TEXT_MUTED, font=FONT_SUBTITLE)
        
    else:
        sub_t = (t - 79.2) / (T_ACT6_END - 79.2)
        ref_img = get_image("assets/references/ref3_latest_male_night.png")
        scale = 1.05 + 0.12 * ease_in_out(sub_t)
        bg = render_cinematic_crop(ref_img, WIDTH, HEIGHT, scale, pan_x=0.0, pan_y=-0.04)
        img = apply_bottom_scrim(bg)
        draw = ImageDraw.Draw(img)
        draw_tiny_brand(draw)
        
        reveal = min(1.0, (t - 79.2) / 0.5)
        y_off = int((1.0 - reveal) * 16)
        
        draw_pill_badge(draw, "ROADMAP // AMBITION", (100, HEIGHT - 240 + y_off), border_color=ACCENT_GOLD, text_color=ACCENT_GOLD)
        draw.text((100, HEIGHT - 175 + y_off), "Your World.", fill=TEXT_CREAM, font=FONT_HERO)
        draw.text((100, HEIGHT - 90 + y_off), "One storyteller. A production workflow within reach.", fill=TEXT_MUTED, font=FONT_SUBTITLE)

    return img

# -----------------------------------------------------------------------------
# ACT 7: TITLE LOGO & CONCLUSION (83.19s - 90.00s)
# -----------------------------------------------------------------------------
def render_act7(fidx, t):
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_DARK)
    
    ref_img = get_image("assets/references/ref3_latest_male_night.png")
    if ref_img:
        sub_t = (t - T_ACT6_END) / (TOTAL_DURATION - T_ACT6_END)
        scale = 1.15 + 0.05 * ease_in_out(sub_t)
        bg = render_cinematic_crop(ref_img, WIDTH, HEIGHT, scale, 0.0, 0.0)
        enhancer = ImageEnhance.Brightness(bg)
        bg_dark = enhancer.enhance(0.18)
        img.paste(bg_dark, (0, 0))
        
    draw = ImageDraw.Draw(img)
    draw_tiny_brand(draw)
    
    cy = 280
    draw_pill_badge(draw, "THE ANIMATION WORKFLOW FOR EVERYONE", (WIDTH//2 - 210, cy), bg_color=(14, 22, 38, 240), border_color=ACCENT_CORAL, text_color=ACCENT_CORAL)
    
    logo_text = "code-anime"
    lbbox = FONT_BIG_NUM.getbbox(logo_text)
    lw = lbbox[2] - lbbox[0]
    draw.text(((WIDTH - lw)//2, cy + 65), logo_text, fill=TEXT_CREAM, font=FONT_BIG_NUM)
    
    sub = "One Storyteller. A Production Workflow Within Reach."
    sbbox = FONT_TITLE.getbbox(sub)
    sw = sbbox[2] - sbbox[0]
    draw.text(((WIDTH - sw)//2, cy + 200), sub, fill=ACCENT_CYAN, font=FONT_TITLE)
    
    draw.line([(WIDTH//2 - 250, cy + 270), (WIDTH//2 + 250, cy + 270)], fill=(255, 255, 255, 35), width=1)
    
    tagline = "Your world deserves to move."
    tbbox = FONT_HEADLINE.getbbox(tagline)
    tw = tbbox[2] - tbbox[0]
    draw.text(((WIDTH - tw)//2, cy + 300), tagline, fill=ACCENT_CORAL, font=FONT_HEADLINE)
    
    meta = "github.com/code-anime • Built for Solo Creators"
    mbbox = FONT_BODY.getbbox(meta)
    mw = mbbox[2] - mbbox[0]
    draw.text(((WIDTH - mw)//2, cy + 400), meta, fill=TEXT_MUTED, font=FONT_BODY)

    return img

# -----------------------------------------------------------------------------
# MASTER FRAME DISPATCHER
# -----------------------------------------------------------------------------
def render_frame(fidx):
    t = fidx / float(FPS)
    if t < T_ACT1_END:
        raw_img = render_act1(fidx, t)
    elif t < T_ACT2_END:
        raw_img = render_act2(fidx, t)
    elif t < T_ACT3_END:
        raw_img = render_act3(fidx, t)
    elif t < T_ACT4_END:
        raw_img = render_act4(fidx, t)
    elif t < T_ACT5_END:
        raw_img = render_act5(fidx, t)
    elif t < T_ACT6_END:
        raw_img = render_act6(fidx, t)
    else:
        raw_img = render_act7(fidx, t)
    
    return apply_editorial_transitions(raw_img, t)

# -----------------------------------------------------------------------------
# MAIN CLI
# -----------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-only", action="store_true")
    parser.add_argument("--render-full", action="store_true")
    parser.add_argument("--out-mp4", default="output/demo90/code-anime-ad-90s.mp4")
    args = parser.parse_args()
    
    os.makedirs("output/demo90/test_frames", exist_ok=True)
    
    if args.test_only:
        test_times = [2.0, 7.0, 12.0, 15.5, 18.0, 21.0, 23.5, 26.0, 31.0, 36.0, 41.0, 48.0, 52.0, 56.0, 59.0, 62.0, 66.0, 70.0, 73.0, 77.0, 81.0, 86.0]
        for tt in test_times:
            fidx = int(tt * FPS)
            im = render_frame(fidx)
            out_p = f"output/demo90/test_frames/ad_frame_{tt:04.1f}s.png"
            im.save(out_p)
            print(f"Rendered test frame {tt:.1f}s -> {out_p}")
        return

    if args.render_full:
        print(f"Starting FINAL CONFORM 90s ad render: {TOTAL_FRAMES} frames @ {FPS}fps...")
        vo_path = "output/demo90/voiceover.wav"
        music_path = "output/demo90/music.wav"
        out_mp4 = args.out_mp4
        
        has_vo = os.path.exists(vo_path)
        has_music = os.path.exists(music_path)
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{WIDTH}x{HEIGHT}",
            "-pix_fmt", "rgba",
            "-r", str(FPS),
            "-i", "-"
        ]
        
        if has_vo and has_music:
            # Score at 1x, amix normalize=0 with alimiter to safe peak
            ffmpeg_cmd.extend([
                "-i", vo_path,
                "-i", music_path,
                "-filter_complex", "[1:a]volume=1.0[v];[2:a]volume=1.0[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];[mix]alimiter=limit=0.95:level=disabled[a]",
                "-map", "0:v",
                "-map", "[a]"
            ])
        elif has_vo:
            ffmpeg_cmd.extend([
                "-i", vo_path,
                "-map", "0:v",
                "-map", "1:a"
            ])
            
        ffmpeg_cmd.extend([
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            out_mp4
        ])
        
        print(f"Spawning ffmpeg process with crf 18 +faststart -> {out_mp4}...")
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        
        try:
            for fidx in range(TOTAL_FRAMES):
                frame_img = render_frame(fidx)
                proc.stdin.write(frame_img.tobytes())
                if fidx % 300 == 0:
                    print(f"Rendered frame {fidx}/{TOTAL_FRAMES} ({fidx/FPS:.1f}s / 90.0s)")
            proc.stdin.close()
        except Exception as e:
            print(f"Error during frame piping: {e}")
            proc.kill()
            sys.exit(1)
            
        retcode = proc.wait()
        print(f"FFmpeg process finished with returncode: {retcode}")
        if retcode != 0:
            print(f"FFmpeg failed with exit code {retcode}")
            sys.exit(retcode)
        print(f"Master conform ad render complete: {out_mp4}")

if __name__ == "__main__":
    main()
