import pygame
import math
import os
from engine import PhysicsEngine, get_nearest_particle, get_nearest_edge
from utils import (open_image_dialog, ask_exact_value, AttachProxy,
                   hit_test_attach, find_attach_target, apply_physical_rotation,
                   ask_exact_text, point_in_polygon, obj_hit_test, UndoManager)
from renderer import Renderer, Camera
from objects import Box, Circle, Triangle, RightTriangle, Constraint, Particle, TrueSpring, ImageBlock, StringObj, PulleyConstraint, PolygonShape, HShape, TShape, CompoundShape
from intro import run_intro

try:
    import cv2
    import numpy as np
except ImportError:
    print("오류: OpenCV 또는 Numpy가 설치되지 않았습니다. 'pip install opencv-python numpy'를 실행해주세요.")
    exit()

def main():
    pygame.init()
    width, height = 1200, 800
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Zenith Motion")
    # 윈도우 아이콘 설정 (타이틀바)
    for _icon_path in ['icon.ico', 'icon.png']:
        if os.path.exists(_icon_path):
            try:
                icon_surf = pygame.image.load(_icon_path).convert_alpha()
                pygame.display.set_icon(icon_surf)
            except Exception:
                pass
            break
    
    if os.path.exists('icon.png'):
        try:
            icon_img = pygame.image.load('icon.png')
            pygame.display.set_icon(icon_img)
        except Exception as e:
            print(f"아이콘 로드 실패: {e}")

    clock = pygame.time.Clock()

    run_intro(screen, clock, width, height)

    engine = PhysicsEngine(2000, 2000)
    cam = Camera()
    renderer = Renderer(screen)

    ui_groups = {
        "1. TOOLS": [('SELECT', 'S'), ('WELD', 'W'), ('HINGE', 'H'), ('VELOCITY', 'V'), ('DELETE', 'D')],
        "2. OBJECTS": [('CIRCLE', 'C'), ('BOX', 'B'), ('TRIANGLE', 'R'), ('RIGHTTRIANGLE', 'J'), ('TSHAPE', 'O'), ('HSHAPE', 'E'), ('IMAGE', 'I')],
        "3. LINKS": [('SPRING', 'P'), ('ATTACH', 'A'), ('STRING', 'L'), ('PULLEY', 'U')],
        "4. EXPORT": [('BAKE', 'K')],
        "5. SYSTEM": [('SETTINGS', 'F1')] 
    }
    
    hotkeys = {
        pygame.K_s: 'SELECT', pygame.K_w: 'WELD', pygame.K_h: 'HINGE', pygame.K_v: 'VELOCITY', pygame.K_d: 'DELETE',
        pygame.K_c: 'CIRCLE', pygame.K_b: 'BOX', pygame.K_r: 'TRIANGLE', pygame.K_j: 'RIGHTTRIANGLE', pygame.K_o: 'TSHAPE', pygame.K_e: 'HSHAPE', pygame.K_i: 'IMAGE',
        pygame.K_p: 'SPRING', pygame.K_a: 'ATTACH', pygame.K_l: 'STRING', pygame.K_u: 'PULLEY',
        pygame.K_k: 'BAKE', pygame.K_F1: 'SETTINGS'
    }

    unit_modes = ['px', 'cm', 'm', 'km']
    unit_scales = [1.0, 1.0, 100.0, 100000.0]
    unit_idx = 2 

    bake_config = {
        'substeps': 10.0, 'world_w': 2000.0, 'world_h': 2000.0,
        'bake_time': 5.0, 'is_baking': False, 'progress': 0.0,
        'frames_total': 0, 'frames_done': 0, 'video_writer': None
    }

    current_mode = 'SELECT'
    drag_obj, info_obj = None, None
    drag_grab_offset = pygame.math.Vector2(0, 0)  # 클릭 시 물체중심↔마우스 오프셋
    drawing, draw_start_pos_world = False, None

    # ── 우클릭 드래그 다중 선택 ─────────────────────────────────────────
    rbox_dragging  = False          # 우클릭 드래그 중
    rbox_start     = None           # 드래그 시작 screen 좌표
    rbox_end       = None           # 드래그 현재 screen 좌표
    selected_objs  = []             # 다중 선택된 오브젝트 목록
    multi_drag_offsets = {}         # {obj: Vector2} 드래그 시 각 물체 오프셋
    multi_drag_active  = False      # 다중 선택 드래그 중
    attach_p1, weld_target = None, None 
    weld_target_pos = None   # 첫 weld 클릭의 월드 좌표 (용수철 끝점 선택용)
    pulley_nodes, hinge_targets = [], []

    # pause 중 실 드래그: 클릭된 파티클 하나만 마우스에 고정
    drag_particle  = None           # StringObj 드래그 시 고정할 파티클
    
    paused = False
    show_axes = True 
    show_velocity_graph = False 
    
    adjusting_friction, adjusting_mass = False, False
    adjusting_angle, adjusting_speed = False, False
    adjusting_rotation = False
    adjusting_air     = False
    adjusting_rest    = False
    adjusting_scale_w = False   # 너비/반지름 슬라이더
    adjusting_scale_h = False   # 높이 슬라이더
    adjusting_spring_k = False  # 스프링 탄성계수 k 슬라이더

    # ── 작업 히스토리 (Ctrl+Z 용) ────────────────────────────────────────
    # ★ 압축 스냅샷 기반 UndoManager (utils.py) — deepcopy 대비 메모리 절감
    undo = UndoManager(max_size=50)
    
    show_sidebar = True
    sidebar_w = 52   # 아이콘 세로 사이드바
    current_sidebar_x = 0.0 

    running = True
    while running:
        if not bake_config['is_baking']:
            raw_dt = min(clock.tick(60) / 1000.0, 0.1)
        else:
            raw_dt = 1.0 / 60.0 

        mouse_pos = pygame.mouse.get_pos()
        mouse_world = cam.to_world(mouse_pos)
        keys = pygame.key.get_pressed()
        
        target_sidebar_x = 0 if show_sidebar else -sidebar_w
        current_sidebar_x += (target_sidebar_x - current_sidebar_x) * (12.0 * raw_dt)

        for obj in engine.objects:
            if not hasattr(obj, 'speed_history'): obj.speed_history = []
            if not paused:
                safe_dt = max(raw_dt, 0.001)
                vx = sum((p.pos.x - p.old_pos.x) for p in obj.particles) / len(obj.particles) / safe_dt
                vy = sum((p.pos.y - p.old_pos.y) for p in obj.particles) / len(obj.particles) / safe_dt
                speed_val = math.hypot(vx, vy) / unit_scales[unit_idx]
                obj.speed_history.append(speed_val)
                if len(obj.speed_history) > 150: obj.speed_history.pop(0)

        if keys[pygame.K_g] and drag_obj:
            if paused:
                # ── pause + 다중선택: 마우스 피벗으로 선택 물체 전체 회전 ──────
                if len(selected_objs) > 1:
                    pivot = pygame.math.Vector2(mouse_world)
                    rotate_objs = set()
                    for sel in selected_objs:
                        weld_gid = getattr(sel, 'weld_group_id', id(sel))
                        for obj in engine.objects:
                            if getattr(obj, 'weld_group_id', id(obj)) == weld_gid:
                                rotate_objs.add(obj)
                    all_parts = [p for obj in rotate_objs for p in obj.particles]
                    ROTATE_SPEED_DEG = 2.0
                    delta_rad = math.radians(ROTATE_SPEED_DEG)
                    cos_a, sin_a = math.cos(delta_rad), math.sin(delta_rad)
                    for p in all_parts:
                        r = p.pos - pivot
                        p.pos = pivot + pygame.math.Vector2(
                            r.x * cos_a - r.y * sin_a,
                            r.x * sin_a + r.y * cos_a)
                        p.old_pos = p.pos.copy()   # pause이므로 속도 0 유지
                    for obj in rotate_objs:
                        if isinstance(obj, Circle):
                            obj.angle += ROTATE_SPEED_DEG
                    # 회전 후 offset 전체 갱신 — click up 시 snap-back 방지
                    pivot_vec = pygame.math.Vector2(mouse_world)
                    if drag_obj and drag_obj.particles:
                        obj_center = sum((p.pos for p in drag_obj.particles),
                                        pygame.math.Vector2()) / len(drag_obj.particles)
                        drag_grab_offset = obj_center - pivot_vec
                    # 다중선택 드래그 오프셋도 회전 후 위치 기준으로 갱신
                    if multi_drag_offsets:
                        for sobj in selected_objs:
                            if id(sobj) not in multi_drag_offsets: continue
                            sc = sum((p.pos for p in sobj.particles),
                                     pygame.math.Vector2()) / len(sobj.particles)
                            multi_drag_offsets[id(sobj)] = sc - pivot_vec
                # ── pause + 단일선택: 기존 방식 (물체 자체 중심 회전) ───────────
                else:
                    apply_physical_rotation(drag_obj, (drag_obj.get_angle() + 2.0) % 360, engine, True)
            else:
                # 회전 중심 = 마우스 위치 (world 좌표)
                weld_gid = getattr(drag_obj, 'weld_group_id', id(drag_obj))
                welded_objs = [obj for obj in engine.objects
                               if getattr(obj, 'weld_group_id', id(obj)) == weld_gid]
                all_parts = [p for obj in welded_objs for p in obj.particles]
                pivot = pygame.math.Vector2(mouse_world)  # 마우스 위치가 회전 중심

                I = sum(p.mass * p.pos.distance_squared_to(pivot) for p in all_parts)
                if I < 1.0: I = 1.0

                torque = 300000.0 * raw_dt
                angular_accel = torque / I

                for p in all_parts:
                    if p.is_static: continue
                    r_vec = p.pos - pivot
                    r_len = r_vec.length()
                    if r_len > 0:
                        tangent_dir = pygame.math.Vector2(-r_vec.y, r_vec.x) / r_len
                        p.old_pos -= tangent_dir * (r_len * angular_accel)

        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                if bake_config['video_writer']: bake_config['video_writer'].release()
                running = False
            
            elif event.type == pygame.MOUSEWHEEL:
                if not show_sidebar or mouse_pos[0] > sidebar_w:
                    world_before = cam.to_world(mouse_pos)
                    cam.zoom *= (1.1 if event.y > 0 else 0.9)
                    cam.zoom = max(0.1, min(cam.zoom, 10.0))
                    world_after = cam.to_world(mouse_pos)
                    cam.offset += (world_after - world_before)
            
            elif event.type == pygame.MOUSEMOTION:
                if pygame.mouse.get_pressed()[1]:
                    cam.offset.x += event.rel[0] / cam.zoom
                    cam.offset.y += event.rel[1] / cam.zoom
                if rbox_dragging:
                    rbox_end = mouse_pos

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    paused = not paused
                    # ★ pause→play 전환 시: VELOCITY 모드로 설정한 초기 속도 적용
                    if not paused:
                        engine.apply_pending_velocities(max(raw_dt, 0.001))
                elif event.key == pygame.K_z and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    snap = undo.pop()   # ★ 압축 스냅샷 복원 (utils.UndoManager)
                    if snap:
                        try:
                            engine.objects            = snap['objects']
                            engine.global_constraints = snap['global_constraints']
                            engine.pulley_constraints = snap['pulley_constraints']

                            # parent 참조 재연결
                            for obj in engine.objects:
                                for p in obj.particles: p.parent = obj
                                for c in obj.constraints: c.parent = obj
                            for c in engine.global_constraints:
                                c.parent = "global"

                            info_obj = None
                            drag_obj = None
                            selected_objs.clear()
                            paused = True
                            engine._rebuild_weld_rest_shapes()
                            print(f"[UNDO] 복원 ({snap.get('label','?')}) — 남은 스택: {len(undo)}")
                        except Exception as e:
                            print(f"[UNDO] 복원 실패: {e}")
                    else:
                        print("[UNDO] 스택이 비어 있음")
                elif event.key == pygame.K_TAB: show_sidebar = not show_sidebar
                elif event.key == pygame.K_t and drag_obj:
                    weld_gid = getattr(drag_obj, 'weld_group_id', id(drag_obj))
                    welded_objs = [obj for obj in engine.objects
                                   if getattr(obj, 'weld_group_id', id(obj)) == weld_gid]
                    is_static = all(p.is_static for obj in welded_objs for p in obj.particles)
                    action_name = 'Pin 고정' if not is_static else 'Pin 해제'
                    print(f'[ACTION] {action_name}: {drag_obj.name}')
                    undo.push(engine, action_name)
                    for obj in welded_objs:
                        for p in obj.particles:
                            p.is_static = not is_static
                            if p.is_static: p.old_pos = p.pos.copy()
                elif event.key == pygame.K_RETURN:
                    if current_mode == 'PULLEY' and len(pulley_nodes) >= 3:
                        engine.add_pulley_constraint(PulleyConstraint(list(pulley_nodes)))
                        pulley_nodes.clear()
                        print('[ACTION] Pulley 생성')
                        undo.push(engine, 'Pulley 생성')
                elif event.key == pygame.K_ESCAPE:
                    pulley_nodes.clear()
                    hinge_targets.clear()
                    attach_p1 = None
                elif event.key in hotkeys:
                    current_mode = hotkeys[event.key]
                    drag_obj, attach_p1, weld_target = None, None, None
                    weld_target_pos = None
                    pulley_nodes, hinge_targets = [], []

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                panel_x = width - 270 - 16
                sc = renderer.slider_coords
                if current_mode == 'BAKE' and panel_x <= mouse_pos[0] <= panel_x + 270:
                    my = mouse_pos[1]
                    if sc['bake_w_y'] - 15 <= my <= sc['bake_w_y'] + 15:
                        val = ask_exact_value("World Width", "월드 가로 크기 입력 (px):", bake_config['world_w'])
                        if val is not None: bake_config['world_w'] = max(100, val); engine.width = bake_config['world_w']
                    elif sc['bake_h_y'] - 15 <= my <= sc['bake_h_y'] + 15:
                        val = ask_exact_value("World Height", "월드 세로 크기 입력 (px):", bake_config['world_h'])
                        if val is not None: bake_config['world_h'] = max(100, val); engine.height = bake_config['world_h']
                    elif sc['bake_sub_y'] - 15 <= my <= sc['bake_sub_y'] + 15:
                        val = ask_exact_value("Sub-steps", "연산 반복 횟수 입력 (1~100):", bake_config['substeps'])
                        if val is not None: bake_config['substeps'] = max(1, int(val))
                    elif sc['bake_dur_y'] - 15 <= my <= sc['bake_dur_y'] + 15:
                        val = ask_exact_value("Bake Time", "출력할 영상 길이 입력 (초):", bake_config['bake_time'])
                        if val is not None: bake_config['bake_time'] = max(1, int(val))
                        
                elif info_obj and current_mode != 'BAKE' and panel_x <= mouse_pos[0] <= panel_x + 260:
                    scale = unit_scales[unit_idx]
                    
                    if 20 + 35 <= mouse_pos[1] <= 20 + 60:
                        cx = sum(p.pos.x for p in info_obj.particles) / len(info_obj.particles)
                        cy = sum(p.pos.y for p in info_obj.particles) / len(info_obj.particles)
                        val_str = ask_exact_text("Position", f"위치 좌표 입력 (X, Y) [{unit_modes[unit_idx]}]:", f"{cx/scale:.1f}, {cy/scale:.1f}")
                        
                        if val_str:
                            try:
                                parts = val_str.split(',')
                                if len(parts) == 2:
                                    new_x = float(parts[0].strip()) * scale
                                    new_y = float(parts[1].strip()) * scale
                                    welded_objs = [o for o in engine.objects if o.collision_group == info_obj.collision_group]
                                    drag_center = sum((p.pos for p in info_obj.particles), pygame.math.Vector2()) / len(info_obj.particles)
                                    offset = pygame.math.Vector2(new_x, new_y) - drag_center
                                    for o in welded_objs:
                                        for p in o.particles:
                                            p.pos += offset
                                            if not paused: p.old_pos += offset
                                            else: p.old_pos = p.pos.copy()
                            except ValueError: pass
                                
                    elif renderer.slider_coords['rot_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['rot_y'] + 12:
                        val = ask_exact_value("Rotation", "물리 회전 각도 입력 (0~360°):", info_obj.get_angle() % 360)
                        if val is not None: apply_physical_rotation(info_obj, val % 360, engine, paused)
                    elif renderer.slider_coords['f_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['f_y'] + 12:
                        val = ask_exact_value("Friction", "마찰력 입력 (0.0~1.0):", info_obj.friction)
                        if val is not None: info_obj.friction = max(0.0, min(1.0, val))
                    elif renderer.slider_coords['m_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['m_y'] + 12:
                        val = ask_exact_value("Mass", "질량 입력 (kg):", info_obj.mass)
                        if val is not None: info_obj.set_mass(max(0.1, val))
                    elif renderer.slider_coords['rest_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['rest_y'] + 12:
                        val = ask_exact_value("Restitution", "반발계수 e (0.0~1.0):", getattr(info_obj, 'restitution', 0.5))
                        if val is not None: info_obj.restitution = max(0.0, min(1.0, val))
                    elif renderer.slider_coords['air_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['air_y'] + 12:
                        val = ask_exact_value("Air Drag", "공기저항 (0.0~1.0):", getattr(info_obj, 'air_drag', 0.0))
                        if val is not None: info_obj.air_drag = max(0.0, min(1.0, val))
                    elif renderer.slider_coords['scale_w_y'] > 0 and renderer.slider_coords['scale_w_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['scale_w_y'] + 12:
                        if hasattr(info_obj, 'resize') and hasattr(info_obj, 'get_size'):
                            if info_obj.name == "Circle":
                                # Circle: 반지름 직접 입력
                                cur_r = info_obj.radius
                                val = ask_exact_value("Radius", "반지름 (px):", cur_r)
                                if val is not None:
                                    info_obj.resize(max(5, val) * 2, max(5, val) * 2)
                                    undo.push(engine, f'Circle 반지름 → {val:.0f}px')
                            else:
                                cur_w, cur_h = info_obj.get_size()
                                val = ask_exact_value("Scale Width", "너비 (px):", cur_w)
                                if val is not None:
                                    info_obj.resize(max(5, val), cur_h)
                                    undo.push(engine, f'Width → {val:.0f}px')
                    elif renderer.slider_coords['scale_h_y'] > 0 and renderer.slider_coords['scale_h_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['scale_h_y'] + 12:
                        if hasattr(info_obj, 'resize') and hasattr(info_obj, 'get_size'):
                            cur_w, cur_h = info_obj.get_size()
                            val = ask_exact_value("Scale Height", "높이 (px):", cur_h)
                            if val is not None:
                                info_obj.resize(cur_w, max(5, val))
                                undo.push(engine, f'Height → {val:.0f}px')
                    elif renderer.slider_coords['spring_k_y'] > 0 and renderer.slider_coords['spring_k_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['spring_k_y'] + 12:
                        # 스프링 탄성계수 k 직접 입력 (k_eff = stiffness * 2e4)
                        if info_obj.name == "Spring" and info_obj.constraints:
                            cur_k = info_obj.constraints[0].stiffness * 2e4
                            val = ask_exact_value("Spring Const", "탄성계수 k (N/m):", cur_k)
                            if val is not None:
                                new_stiff = max(0.0001, min(0.05, val / 2e4))
                                for _c in info_obj.constraints:
                                    if getattr(_c, 'style', '') == 'spring':
                                        _c.stiffness = new_stiff
                                undo.push(engine, f'Spring k → {new_stiff*2e4:.0f} N/m')
                    elif current_mode == 'VELOCITY':
                        
                        if renderer.slider_coords['vel_a_y'] - 15 <= mouse_pos[1] <= renderer.slider_coords['vel_a_y'] + 15:
                            val = ask_exact_value("Angle", "초기 이동 각도 입력 (0~360°):", current_angle)
                            if val is not None:
                                current_angle = math.radians(val % 360.0)
                                info_obj.set_velocity(math.cos(current_angle) * current_speed, math.sin(current_angle) * current_speed, safe_dt)
                        elif renderer.slider_coords['vel_s_y'] - 15 <= mouse_pos[1] <= renderer.slider_coords['vel_s_y'] + 15:
                            val = ask_exact_value("Speed", f"초기 속력 입력 ({unit_modes[unit_idx]}/s):", current_speed / scale)
                            if val is not None:
                                current_speed = val * scale
                                rad_ang = math.radians(current_angle)
                                info_obj.set_velocity(math.cos(rad_ang) * current_speed, math.sin(rad_ang) * current_speed, safe_dt)

                # SELECT/VELOCITY 모드: 우클릭 드래그 다중 선택 시작
                if current_mode in ['SELECT', 'VELOCITY']:
                    panel_x_check = width - 270 - 16
                    sidebar_in = (show_sidebar and mouse_pos[0] <= int(current_sidebar_x) + sidebar_w)
                    panel_in   = (mouse_pos[0] >= panel_x_check)
                    if not sidebar_in and not panel_in:
                        rbox_dragging = True
                        rbox_start    = mouse_pos
                        rbox_end      = mouse_pos

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                if rbox_dragging:
                    rbox_dragging = False
                    # 선택 박스 안의 물체 모두 선택
                    if rbox_start and rbox_end:
                        rx1 = min(rbox_start[0], rbox_end[0])
                        rx2 = max(rbox_start[0], rbox_end[0])
                        ry1 = min(rbox_start[1], rbox_end[1])
                        ry2 = max(rbox_start[1], rbox_end[1])
                        if rx2 - rx1 > 4 or ry2 - ry1 > 4:  # 최소 크기 이상
                            selected_objs = []
                            for obj in engine.objects:
                                sc_center = cam.to_screen(
                                    sum((p.pos for p in obj.particles),
                                        pygame.math.Vector2()) / len(obj.particles))
                                if rx1 <= sc_center[0] <= rx2 and ry1 <= sc_center[1] <= ry2:
                                    selected_objs.append(obj)
                            if selected_objs:
                                info_obj = selected_objs[-1]  # 패널에는 마지막 선택 표시
                    rbox_start = rbox_end = None

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if current_mode == 'SETTINGS':
                    # 탭 클릭 확인
                    tabs_rects = renderer.slider_coords.get('settings_tabs', [])
                    clicked_tab = False
                    for ti, (tx, ty, tw, th) in enumerate(tabs_rects):
                        if pygame.Rect(tx, ty, tw, th).collidepoint(mouse_pos):
                            renderer._settings_tab = ti
                            clicked_tab = True
                            break
                    if clicked_tab:
                        continue
                    # 닫기 버튼
                    cr = renderer.slider_coords.get('settings_close')
                    if cr and pygame.Rect(cr).collidepoint(mouse_pos):
                        current_mode = 'SELECT'
                        continue
                    # 대화상자 바깥 클릭 → 닫기
                    DW, DH = 580, 520
                    DX = width // 2 - DW // 2
                    DY = height // 2 - DH // 2
                    if not pygame.Rect(DX, DY, DW, DH).collidepoint(mouse_pos):
                        current_mode = 'SELECT'
                    continue
                    
                panel_x = width - 270 - 16
                if info_obj and current_mode != 'BAKE' and panel_x <= mouse_pos[0] <= panel_x + 260:
                    if 20 + 60 <= mouse_pos[1] <= 20 + 115:
                        show_velocity_graph = not show_velocity_graph
                        continue

                if current_mode not in ['BAKE', 'SETTINGS']:
                    # renderer와 동일한 all_items 구성 (오브젝트 + attach 막대)
                    _attach_cs = [c for c in engine.global_constraints
                                  if getattr(c, 'is_solid', False)
                                  and getattr(c, 'style', 'line') not in ('weld', 'hinge')]
                    _all_items = list(engine.objects) + _attach_cs
                    max_display = 15
                    disp_items  = _all_items[-max_display:]
                    list_w = 190
                    list_h = 36 + len(disp_items) * 20
                    if not disp_items: list_h = 56
                    list_x = width - list_w - 16
                    list_y = height - list_h - 16

                    if list_x <= mouse_pos[0] <= list_x + list_w and list_y <= mouse_pos[1] <= list_y + list_h:
                        rel_y = mouse_pos[1] - (list_y + 32)
                        idx   = int(rel_y / 20)
                        if 0 <= idx < len(disp_items):
                            item = disp_items[idx]
                            if hasattr(item, 'particles'):   # 일반 오브젝트
                                info_obj = item
                            else:                            # attach Constraint → AttachProxy로 래핑
                                info_obj = AttachProxy(item)
                            current_mode = 'SELECT'
                            drag_obj = None
                            continue
                            
                if bake_config['is_baking']: continue 

                adjusting_friction, adjusting_mass = False, False
                adjusting_angle, adjusting_speed, adjusting_rotation = False, False, False
                adjusting_air     = False
                adjusting_rest    = False
                adjusting_scale_w = False
                adjusting_scale_h = False
                adjusting_spring_k = False
                
                if current_mode == 'BAKE' and panel_x <= mouse_pos[0] <= panel_x + 270:
                    sc = renderer.slider_coords
                    rel_x = mouse_pos[0] - (panel_x + 14)
                    ratio = max(0.0, min(1.0, rel_x / (270 - 28)))
                    my = mouse_pos[1]

                    if sc['bake_w_y'] - 12 <= my <= sc['bake_w_y'] + 12:
                        bake_config['world_w'] = 1000 + ratio * 9000; engine.width = bake_config['world_w']; continue
                    if sc['bake_h_y'] - 12 <= my <= sc['bake_h_y'] + 12:
                        bake_config['world_h'] = 1000 + ratio * 9000; engine.height = bake_config['world_h']; continue
                    if sc['bake_sub_y'] - 12 <= my <= sc['bake_sub_y'] + 12:
                        bake_config['substeps'] = max(1, int(1 + ratio * 99)); continue
                    if sc['bake_dur_y'] - 12 <= my <= sc['bake_dur_y'] + 12:
                        bake_config['bake_time'] = max(1, int(1 + ratio * 59)); continue
                    if sc['bake_btn_y1'] <= my <= sc['bake_btn_y2']:
                        bake_config['is_baking'] = True
                        bake_config['frames_total'] = int(bake_config['bake_time'] * 60)
                        bake_config['frames_done'] = 0
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        bake_config['video_writer'] = cv2.VideoWriter('physics_bake_output.mp4', fourcc, 60.0, (width, height))
                        paused = False 
                        continue

                if info_obj and current_mode != 'BAKE' and panel_x <= mouse_pos[0] <= panel_x + 260:
                    if renderer.slider_coords['rot_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['rot_y'] + 12: adjusting_rotation = True; continue
                    if renderer.slider_coords['f_y']   - 12 <= mouse_pos[1] <= renderer.slider_coords['f_y']   + 12: adjusting_friction = True; continue
                    if renderer.slider_coords['m_y']   - 12 <= mouse_pos[1] <= renderer.slider_coords['m_y']   + 12: adjusting_mass = True; continue
                    if renderer.slider_coords['rest_y']    - 12 <= mouse_pos[1] <= renderer.slider_coords['rest_y']    + 12: adjusting_rest    = True; continue
                    if renderer.slider_coords['air_y']     - 12 <= mouse_pos[1] <= renderer.slider_coords['air_y']     + 12: adjusting_air     = True; continue
                    if renderer.slider_coords['scale_w_y'] > 0 and renderer.slider_coords['scale_w_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['scale_w_y'] + 12: adjusting_scale_w = True; continue
                    if renderer.slider_coords['scale_h_y'] > 0 and renderer.slider_coords['scale_h_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['scale_h_y'] + 12: adjusting_scale_h = True; continue
                    if renderer.slider_coords['spring_k_y'] > 0 and renderer.slider_coords['spring_k_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['spring_k_y'] + 12: adjusting_spring_k = True; continue
                    # Z-Layer +/- 버튼
                    zsc = renderer.slider_coords
                    zm = zsc['z_minus_btn']; zp = zsc['z_plus_btn']
                    if pygame.Rect(*zm).collidepoint(mouse_pos) and info_obj:
                        info_obj.z_layer = max(-9, getattr(info_obj, 'z_layer', 0) - 1)
                        print(f'[ACTION] Z-Layer: {info_obj.name} → {info_obj.z_layer}')
                        undo.push(engine, f'Z-Layer {info_obj.z_layer}'); continue
                    if pygame.Rect(*zp).collidepoint(mouse_pos) and info_obj:
                        info_obj.z_layer = min(9, getattr(info_obj, 'z_layer', 0) + 1)
                        print(f'[ACTION] Z-Layer: {info_obj.name} → {info_obj.z_layer}')
                        undo.push(engine, f'Z-Layer {info_obj.z_layer}'); continue
                    # Attach 충돌 ON/OFF 버튼
                    cb = zsc.get('collision_btn', (0,0,0,0))
                    if cb[2] > 0 and getattr(info_obj, 'name', '') == 'Attach':
                        cbtn_rect = pygame.Rect(*cb)
                        if cbtn_rect.collidepoint(mouse_pos):
                            _c = info_obj.constraint
                            sw2_half = cb[2] // 2
                            # 왼쪽 절반 = ON, 오른쪽 절반 = OFF
                            if mouse_pos[0] < cb[0] + sw2_half:
                                _c.no_collision = False
                                print(f'[ACTION] Attach 충돌 ON')
                            else:
                                _c.no_collision = True
                                print(f'[ACTION] Attach 충돌 OFF')
                            continue
                    if current_mode == 'VELOCITY':
                        if renderer.slider_coords['vel_a_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['vel_a_y'] + 12: adjusting_angle = True; continue
                        if renderer.slider_coords['vel_s_y'] - 12 <= mouse_pos[1] <= renderer.slider_coords['vel_s_y'] + 12: adjusting_speed = True; continue
                
                toggle_rect = pygame.Rect(current_sidebar_x + sidebar_w, 20, 24, 40)
                if toggle_rect.collidepoint(mouse_pos):
                    show_sidebar = not show_sidebar; continue

                if show_sidebar and mouse_pos[0] <= current_sidebar_x + sidebar_w:
                    # 토글 버튼: renderer._toggle_rects 참조
                    if hasattr(renderer, '_toggle_rects'):
                        toggle_actions = [
                            lambda: setattr(engine, 'gravity_enabled', not engine.gravity_enabled),
                            lambda: globals().update({'show_axes': not show_axes}),
                            lambda: globals().update({'unit_idx': (unit_idx+1) % len(unit_modes)}),
                        ]
                        for ti, (trect, active, tlbl) in enumerate(renderer._toggle_rects):
                            if trect.collidepoint(mouse_pos):
                                if ti == 0: engine.gravity_enabled = not engine.gravity_enabled
                                elif ti == 1: show_axes = not show_axes
                                elif ti == 2: unit_idx = (unit_idx + 1) % len(unit_modes)
                                continue

                    # 세로 아이콘 사이드바 히트박스 (renderer._btn_rects와 동일 계산)
                    clicked_ui = False
                    # renderer._btn_rects 직접 참조 (자동 크기와 완벽히 동기화)
                    clicked_ui = False
                    if hasattr(renderer, '_btn_rects'):
                        for btn, brect in renderer._btn_rects.items():
                            if brect.collidepoint(mouse_pos):
                                current_mode = btn
                                drag_obj, attach_p1, weld_target = None, None, None
                                weld_target_pos = None
                                pulley_nodes, hinge_targets = [], []
                                clicked_ui = True
                                break
                    if clicked_ui: continue

                if current_mode in ['SELECT', 'VELOCITY']:
                    info_obj = None
                    drag_particle = None
                    hit_any = False
                    for obj in reversed(engine.objects):
                        if obj_hit_test(obj, mouse_world, cam):
                            info_obj = obj
                            hit_any = True
                            if current_mode == 'SELECT':
                                drag_obj = obj
                                obj_center = sum((p.pos for p in obj.particles),
                                                pygame.math.Vector2()) / len(obj.particles)
                                drag_grab_offset = obj_center - pygame.math.Vector2(mouse_world)
                                # ── 실(StringObj): 클릭 위치에 가장 가까운 파티클을 고정 ──
                                if isinstance(obj, StringObj):
                                    mp = pygame.math.Vector2(mouse_world)
                                    drag_particle = min(obj.particles,
                                        key=lambda p: p.pos.distance_squared_to(mp))
                                if obj in selected_objs and len(selected_objs) > 1:
                                    multi_drag_active = True
                                    multi_drag_offsets.clear()
                                    for sobj in selected_objs:
                                        sc = sum((p.pos for p in sobj.particles),
                                                 pygame.math.Vector2()) / len(sobj.particles)
                                        multi_drag_offsets[id(sobj)] = sc - pygame.math.Vector2(mouse_world)
                                elif keys[pygame.K_g] and len(selected_objs) > 1:
                                    multi_drag_active = False
                                else:
                                    multi_drag_active = False
                                    selected_objs = [obj]
                            break
                    # 오브젝트 히트 없으면 attach 막대 히트 테스트
                    if not hit_any and current_mode == 'SELECT':
                        proxy = hit_test_attach(engine, mouse_world, threshold=10.0)
                        if proxy:
                            info_obj = proxy
                            hit_any = True
                            # attach는 드래그 이동 없음 — drag_obj는 설정 안 함
                    # 허공 클릭 → 선택 전체 해제
                    if not hit_any and current_mode == 'SELECT':
                        selected_objs = []
                        multi_drag_active = False
                elif current_mode == 'DELETE':
                    for obj in reversed(engine.objects):
                        if obj_hit_test(obj, mouse_world, cam):
                            print(f'[ACTION] 오브젝트 삭제: {obj.name}'); engine.remove_object(obj); undo.push(engine, f'삭제: {obj.name}')
                            if info_obj == obj: info_obj = None
                            break
                elif current_mode == 'WELD':
                    clicked_obj = None
                    for obj in reversed(engine.objects):
                        if obj_hit_test(obj, mouse_world, cam):
                            clicked_obj = obj; break
                    if clicked_obj:
                        if weld_target is None:
                            weld_target = clicked_obj
                            weld_target_pos = pygame.math.Vector2(mouse_world)
                        else:
                            print(f'[ACTION] Weld: {weld_target.name} + {clicked_obj.name}')
                            # 클릭 위치를 함께 전달 → 용수철은 클릭한 끝점이 weld 지점이 됨
                            engine.weld_objects(weld_target, clicked_obj,
                                                pos1=weld_target_pos,
                                                pos2=pygame.math.Vector2(mouse_world))
                            weld_target = None; weld_target_pos = None
                            undo.push(engine, f'Weld')
                elif current_mode == 'HINGE':
                    if len(hinge_targets) < 2:
                        clicked_obj = None
                        for obj in reversed(engine.objects):
                            if obj_hit_test(obj, mouse_world, cam):
                                clicked_obj = obj; break
                        if clicked_obj and clicked_obj not in hinge_targets: hinge_targets.append(clicked_obj)
                    else:
                        obj1, obj2 = hinge_targets[0], hinge_targets[1]
                        obj2.collision_group = obj1.collision_group
                        def attach_pin(obj, pos):
                            pt = Particle(pos.x, pos.y, radius=3, mass=0.5)
                            existing_particles = list(obj.particles)
                            obj.particles.append(pt); pt.parent = obj
                            if isinstance(obj, (StringObj, TrueSpring)):
                                closest = min(existing_particles, key=lambda p: p.pos.distance_squared_to(pos))
                                obj.constraints.append(Constraint(pt, closest, stiffness=1.0, is_solid=False, parent=obj))
                            else:
                                for cp in existing_particles:
                                    obj.constraints.append(Constraint(pt, cp, stiffness=1.0, is_solid=False, parent=obj))
                            return pt
                        pin1 = attach_pin(obj1, mouse_world)
                        pin2 = attach_pin(obj2, mouse_world)
                        engine.add_global_constraint(Constraint(pin1, pin2, length=0, stiffness=1.0, style="hinge"))
                        hinge_targets.clear()
                        print('[ACTION] Hinge 생성')
                        undo.push(engine, 'Hinge 생성')
                elif current_mode == 'PULLEY':
                    target_p = get_nearest_particle(engine, mouse_world, 25)
                    if not target_p:
                        closest_pt, edge, obj = get_nearest_edge(engine, mouse_world, 20)
                        if closest_pt:
                            target_p = Particle(closest_pt.x, closest_pt.y, radius=3, mass=0.5)
                            obj.particles.append(target_p); target_p.parent = obj
                            if edge == "CIRCLE": obj.constraints.append(Constraint(target_p, obj.particles[0], length=obj.radius, stiffness=1.0, parent=obj))
                            else: obj.constraints.extend([Constraint(target_p, edge.p1, stiffness=1.0, parent=obj), Constraint(target_p, edge.p2, stiffness=1.0, parent=obj)])
                    if target_p: pulley_nodes.append(target_p)
                elif current_mode == 'ATTACH':
                    # 클릭 위치에서 attach 대상 파티클 탐색/생성
                    # - 기존 파티클 근처: 재사용
                    # - 실/스프링 선분 위: 보간점에 새 파티클
                    # - 폴리곤 내부: 클릭 위치에 새 파티클 + 모든 기존 파티클과 연결
                    # - 외곽선 근처: 선분 위 보간점
                    target_p = find_attach_target(engine, mouse_world, cam)
                    if target_p:
                        if attach_p1 is None:
                            attach_p1 = target_p
                            print(f'[ACTION] Attach 첫번째 선택: {getattr(target_p.parent, "name", "?")}'
                                  f' @ ({target_p.pos.x:.0f}, {target_p.pos.y:.0f})')
                        elif target_p != attach_p1:
                            # 같은 물체끼리는 연결 무시
                            if target_p.parent is attach_p1.parent:
                                print('[ATTACH] 같은 물체 — 무시')
                                attach_p1 = None
                            else:
                                print(f'[ACTION] Attach 연결: '
                                      f'{getattr(attach_p1.parent, "name", "?")} ↔ '
                                      f'{getattr(target_p.parent, "name", "?")}')
                                engine.add_global_constraint(
                                    Constraint(attach_p1, target_p, stiffness=1.0, is_solid=True))
                                undo.push(engine, 'Attach')
                                # 충돌 그룹 병합 (폭발 방지)
                                if attach_p1.parent and target_p.parent:
                                    old_group    = target_p.parent.collision_group
                                    target_group = attach_p1.parent.collision_group
                                    for obj in engine.objects:
                                        if obj.collision_group == old_group:
                                            obj.collision_group = target_group
                                attach_p1 = None
                else:
                    if current_mode not in ['BAKE', 'SETTINGS']: drawing = True; draw_start_pos_world = mouse_world

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                adjusting_friction, adjusting_mass = False, False
                adjusting_angle, adjusting_speed, adjusting_rotation = False, False, False
                adjusting_air     = False
                adjusting_rest    = False
                adjusting_scale_w = False
                adjusting_scale_h = False
                adjusting_spring_k = False
                drag_particle = None   # 실 파티클 고정 해제
                if current_mode == 'SELECT':
                    if drag_obj is not None:
                        if keys[pygame.K_g] and len(selected_objs) > 1:
                            # G 회전 완료 — 회전된 상태 그대로 undo 저장
                            undo.push(engine, '회전: 다중선택')
                        else:
                            print(f'[ACTION] 이동: {drag_obj.name}')
                            undo.push(engine, f'이동: {drag_obj.name}')
                    drag_obj = None
                    multi_drag_active = False
                elif current_mode == 'VELOCITY':
                    drag_obj = None
                elif drawing:
                    drawing = False
                    s_x, s_y = draw_start_pos_world
                    c_x, c_y = mouse_world
                    w, h = abs(s_x - c_x), abs(s_y - c_y)
                    dist = math.hypot(c_x - s_x, c_y - s_y)
                    
                    if current_mode in ['BOX', 'TRIANGLE', 'RIGHTTRIANGLE', 'TSHAPE', 'HSHAPE', 'IMAGE'] and w > 10 and h > 10:
                        cx, cy = (s_x + c_x) / 2, (s_y + c_y) / 2
                        if current_mode == 'BOX': obj = Box(cx, cy, w, h)
                        elif current_mode == 'TRIANGLE': obj = Triangle(cx, cy, w, h)
                        elif current_mode == 'TSHAPE': obj = TShape(cx, cy, w, h)
                        elif current_mode == 'HSHAPE': obj = HShape(cx, cy, w, h)
                        elif current_mode == 'RIGHTTRIANGLE': obj = RightTriangle(cx, cy, w, h)
                        elif current_mode == 'IMAGE': 
                            img_path = open_image_dialog()
                            if img_path: obj = ImageBlock(cx, cy, w, h, img_path)
                            else: continue
                        print(f'[ACTION] 생성: {obj.name}'); engine.add_object(obj); info_obj = obj; undo.push(engine, f'생성: {obj.name}')
                    elif current_mode == 'CIRCLE' and dist > 5: obj = Circle(s_x, s_y, dist); print(f'[ACTION] 생성: Circle'); engine.add_object(obj); info_obj = obj; undo.push(engine, '생성: Circle')
                    elif current_mode == 'SPRING' and dist > 20: print('[ACTION] 생성: Spring'); engine.add_object(TrueSpring(s_x, s_y, c_x, c_y)); undo.push(engine, '생성: Spring')
                    elif current_mode == 'STRING' and dist > 15: print('[ACTION] 생성: String'); engine.add_object(StringObj(s_x, s_y, c_x, c_y, max(3, int(dist / 15)))); undo.push(engine, '생성: String')

        if info_obj and pygame.mouse.get_pressed()[0] and (adjusting_friction or adjusting_mass or adjusting_angle or adjusting_speed or adjusting_rotation or adjusting_air or adjusting_rest or adjusting_scale_w or adjusting_scale_h or adjusting_spring_k):
            panel_x2 = width - 270 - 16
            slider_x = panel_x2 + 14
            slider_w = 270 - 28
            rel_x = mouse_pos[0] - slider_x
            ratio = max(0.0, min(1.0, rel_x / slider_w))
            
            if adjusting_rotation:
                apply_physical_rotation(info_obj, ratio * 360.0, engine, paused)
            elif adjusting_friction: info_obj.friction = ratio * 0.1
            elif adjusting_mass: info_obj.set_mass(0.1 + ratio * 49.9)
            elif adjusting_rest: info_obj.restitution = ratio
            elif adjusting_air:  info_obj.air_drag = ratio
            elif adjusting_spring_k:
                # 로그 매핑: ratio 0~1 → stiffness 0.0001~0.05 (renderer와 일치)
                if info_obj.name == "Spring" and info_obj.constraints:
                    K_MIN, K_MAX = 0.0001, 0.05
                    new_stiff = K_MIN * (K_MAX / K_MIN) ** ratio
                    for _c in info_obj.constraints:
                        if getattr(_c, 'style', '') == 'spring':
                            _c.stiffness = new_stiff
            elif adjusting_scale_w or adjusting_scale_h:
                if hasattr(info_obj, 'resize') and hasattr(info_obj, 'get_size'):
                    from objects import Circle as _C
                    if isinstance(info_obj, _C) and adjusting_scale_w:
                        # Circle: ratio → 반지름 직접 적용 (MAX_R=400)
                        new_r = max(5, ratio * 400.0)
                        info_obj.resize(new_r * 2, new_r * 2)
                    else:
                        cur_w, cur_h = info_obj.get_size()
                        max_scale = 800.0
                        if adjusting_scale_w:
                            new_w = max(5, ratio * max_scale)
                            new_h = cur_h
                        else:
                            new_w = cur_w
                            new_h = max(5, ratio * max_scale)
                        info_obj.resize(new_w, new_h)
            elif adjusting_angle or adjusting_speed:
                safe_dt = max(raw_dt, 0.001)
                vx = sum((p.pos.x - p.old_pos.x) for p in info_obj.particles) / len(info_obj.particles) / safe_dt
                vy = sum((p.pos.y - p.old_pos.y) for p in info_obj.particles) / len(info_obj.particles) / safe_dt
                current_speed = math.hypot(vx, vy)
                current_angle = math.atan2(vy, vx)
                
                if adjusting_angle: current_angle = math.radians(ratio * 360.0)
                elif adjusting_speed: current_speed = ratio * 2000.0
                
                new_vx = math.cos(current_angle) * current_speed
                new_vy = math.sin(current_angle) * current_speed
                info_obj.set_velocity(new_vx, new_vy, safe_dt)

        elif current_mode == 'SELECT' and drag_obj and pygame.mouse.get_pressed()[0] and not keys[pygame.K_g]:
            if multi_drag_active and multi_drag_offsets:
                # 다중 선택 드래그
                for sobj in selected_objs:
                    if id(sobj) not in multi_drag_offsets: continue
                    target_c = pygame.math.Vector2(mouse_world) + multi_drag_offsets[id(sobj)]
                    cur_c = sum((p.pos for p in sobj.particles),
                                pygame.math.Vector2()) / len(sobj.particles)
                    off = target_c - cur_c
                    for p in sobj.particles:
                        p.pos += off
                        if not paused: p.old_pos = p.pos.copy()
                        else: p.old_pos += off
            elif paused and drag_particle is not None:
                # ── pause 중 실(StringObj) 드래그: 클릭한 파티클만 마우스에 고정 ──
                # paused_solve()가 constraint로 나머지 파티클을 끌어당김
                drag_particle.pos     = pygame.math.Vector2(mouse_world)
                drag_particle.old_pos = drag_particle.pos.copy()
            else:
                # 일반 단일 선택 드래그
                weld_gid = getattr(drag_obj, 'weld_group_id', id(drag_obj))
                move_objs = [obj for obj in engine.objects
                             if getattr(obj, 'weld_group_id', id(obj)) == weld_gid]
                target_center = pygame.math.Vector2(mouse_world) + drag_grab_offset
                drag_center = sum((p.pos for p in drag_obj.particles),
                                  pygame.math.Vector2()) / len(drag_obj.particles)
                offset = target_center - drag_center
                for obj in move_objs:
                    for p in obj.particles:
                        p.pos += offset
                        if not paused: p.old_pos = p.pos.copy()
                        else: p.old_pos += offset

        if not paused:
            current_substeps = int(bake_config['substeps'])
            step_dt = raw_dt / current_substeps
            for obj in engine.objects:
                for p in obj.particles: p.normal_offset = pygame.math.Vector2(0, 0)
                obj.tension_acc = 0.0
                obj.spring_acc  = 0.0
                obj.int_acc     = 0.0
                obj.normal_acc  = 0.0
                obj.stress_max  = 0.0
            engine._current_substeps = current_substeps
            engine._contact_normal_impulse.clear()

            # 탄성 반발 pre-pass (프레임당 1회 — substep 루프 전에 실행)
            engine.apply_restitution()

            for _ in range(current_substeps):
                engine.update(step_dt)
        else:
            # pause 중: 속도·중력 없이 constraint + 충돌 위치 보정만 수행
            # → attach/weld 늘어짐 방지, 물체 충돌 유지
            engine.paused_solve()


        renderer.draw(engine, current_mode, drawing, draw_start_pos_world, mouse_world, attach_p1, weld_target, pulley_nodes, hinge_targets, paused, info_obj, raw_dt, int(current_sidebar_x), ui_groups, cam, unit_idx, unit_scales, unit_modes, bake_config, show_axes, show_velocity_graph, selected_objs=selected_objs, rbox_start=rbox_start, rbox_end=rbox_end, mouse_screen=mouse_pos)

        if bake_config['is_baking']:
            frame = pygame.surfarray.array3d(screen)
            frame = np.transpose(frame, (1, 0, 2)) 
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            bake_config['video_writer'].write(frame)
            
            bake_config['frames_done'] += 1
            bake_config['progress'] = bake_config['frames_done'] / bake_config['frames_total']
            
            if bake_config['frames_done'] >= bake_config['frames_total']:
                print(f"베이킹 완료! 파일명: physics_bake_output.mp4")
                bake_config['is_baking'] = False
                bake_config['video_writer'].release()
                bake_config['video_writer'] = None
                paused = True 

    pygame.quit()

if __name__ == "__main__":
    main()