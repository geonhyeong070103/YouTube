import pygame
import math
from objects import Box, Circle, Triangle, RightTriangle, StringObj, TrueSpring, ImageBlock, PolygonShape, HShape, TShape, CompoundShape

class Camera:
    def __init__(self):
        self.offset = pygame.math.Vector2(0, 0)
        self.zoom = 1.0

    def to_screen(self, pos):
        x = (pos[0] + self.offset.x) * self.zoom
        y = (pos[1] + self.offset.y) * self.zoom
        return (int(x), int(y))

    def to_world(self, pos):
        x = pos[0] / self.zoom - self.offset.x
        y = pos[1] / self.zoom - self.offset.y
        return pygame.math.Vector2(x, y)

    def scale(self, value):
        return value * self.zoom


def draw_zigzag(surface, color, p1, p2, width, cam):
    delta = p2 - p1
    dist = delta.length()
    if dist < 1:
        return
    dir_vec = delta / dist
    norm_vec = pygame.math.Vector2(-dir_vec.y, dir_vec.x)
    coils = max(3, int(dist / 15))
    points = [cam.to_screen(p1)]
    step = dist / (coils * 2 + 1)
    amp = 12
    for i in range(1, coils * 2 + 1):
        base = p1 + dir_vec * (step * i)
        offset = norm_vec * amp if i % 2 == 1 else norm_vec * -amp
        points.append(cam.to_screen(base + offset))
    points.append(cam.to_screen(p2))
    pygame.draw.lines(surface, color, False, points, max(1, int(width * cam.zoom)))


# ─────────────────────────────────────────────────────────────────
#  색상 팔레트 — Interactive Physics 클래식 스타일
# ─────────────────────────────────────────────────────────────────
C_BG        = (192, 192, 192)   # Win95 클래식 회색 (캔버스 바깥)
C_CANVAS    = (255, 255, 255)   # 시뮬레이션 캔버스 흰색
C_GRID      = (220, 220, 220)   # 격자 연회색
C_SIDEBAR   = (192, 192, 192)   # Win95 패널 배경
C_SIDEBAR_B = (212, 208, 200)   # Win95 버튼 기본 (raised)
C_SIDEBAR_A = (0,   0,   128)   # Win95 선택 네이비
C_PANEL     = (192, 192, 192, 245)  # 패널
C_PANEL_BD  = (128, 128, 128)   # Win95 테두리 어두운면
C_PANEL_LT  = (255, 255, 255)   # Win95 테두리 밝은면
C_TEXT      = (0,   0,   0)     # 검정 텍스트
C_TEXT_DIM  = (128, 128, 128)   # 회색 텍스트
C_ACCENT    = (0,   0,   128)   # 네이비 포인트
C_GREEN     = (0,   128,  0)    # 초록
C_RED       = (200,  0,   0)    # 빨강 (힘 벡터)
C_YELLOW    = (255, 255,  0)    # 노랑
C_OBJ       = (0,  128, 128)    # IP 청록색 물체
C_OBJ_SEL   = (255, 255, 0)    # 선택된 물체 노랑
C_SLIDER_BG = (128, 128, 128)
C_SLIDER_FG = (0,   0,   128)
C_SLIDER_TH = (212, 208, 200)
C_FORCE_VEC = (220,  20,  20)   # 힘 벡터 빨강 화살표
C_VEL_VEC   = (0,   160,  0)    # 속도 벡터 초록


def _pill(surf, color, rect, r=6, border_color=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border_color:
        pygame.draw.rect(surf, border_color, rect, 1, border_radius=r)


def _win95_trackbar(surf, sx, sy, sw, ratio, label, value_str, font, bar_color=None):
    """Win95 trackbar 스타일 슬라이더.
    트랙: sunken 홈, 핸들: raised 사각 버튼.
    반환: 핸들 중심 절대 y.
    """
    # 라벨
    surf.blit(font.render(label, True, C_TEXT_DIM), (sx, sy))
    # 값 우측 정렬
    v_surf = font.render(value_str, True, C_TEXT)
    surf.blit(v_surf, (sx + sw - v_surf.get_width(), sy))

    track_y  = sy + 16
    track_cx = track_y + 3   # 중심 y

    # 트랙 홈 (sunken, 4px 높이)
    pygame.draw.rect(surf, (128,128,128), (sx, track_y,     sw, 4))
    pygame.draw.rect(surf, (255,255,255), (sx, track_y + 2, sw, 2))

    # 채움 (bar_color 지정 시)
    if bar_color:
        fill_w = int(ratio * sw)
        if fill_w > 0:
            pygame.draw.rect(surf, bar_color, (sx, track_y, fill_w, 4))

    # Win95 trackbar 핸들 (사각 raised 버튼, 10×16)
    hx = int(sx + ratio * sw)
    pygame.draw.rect(surf, C_SIDEBAR_B, (hx-5, track_y-6, 10, 16))
    pygame.draw.lines(surf, (255,255,255), False,
        [(hx-5, track_y+9), (hx-5, track_y-6), (hx+4, track_y-6)], 1)
    pygame.draw.lines(surf, (64,64,64), False,
        [(hx-5, track_y+9), (hx+4, track_y+9), (hx+4, track_y-6)], 1)

    return track_cx  # 핸들 중심 y


def _draw_slider(surf, sx, sy, sw, ratio, label, value_str, font, active=False):
    """_win95_trackbar 래퍼 (기존 호출 유지)"""""
    return _win95_trackbar(surf, sx, sy, sw, ratio, label, value_str, font)


class Renderer:
    def __init__(self, screen):
        import os
        self.screen = screen
        # Interactive Physics 클래식 폰트 (작고 선명한 sans)
        _fn = "malgungothic, applegothic, arial, sans"
        self.font       = pygame.font.SysFont(_fn, 12, bold=False)
        self.title_font = pygame.font.SysFont(_fn, 11, bold=True)
        self.big_font   = pygame.font.SysFont(_fn, 18, bold=True)
        self.icon_font  = pygame.font.SysFont(_fn, 10)

        # 그룹별 색상 (사이드바 섹션 구분용)
        self._group_colors = {
            "1. TOOLS":   (0, 0, 0),
            "2. OBJECTS": (0, 0, 0),
            "3. LINKS":   (0, 0, 0),
            "4. EXPORT":  (0, 0, 0),
            "5. SYSTEM":  (0, 0, 0),
        }

        # 버튼 이름 → PNG 아이콘 (소문자.png)
        _icon_map = {
            'SELECT': 'select', 'WELD': 'weld', 'HINGE': 'hinge',
            'VELOCITY': 'velocity', 'DELETE': 'delete',
            'CIRCLE': 'circle', 'BOX': 'box', 'TRIANGLE': 'triangle',
            'TSHAPE': 'tshape', 'HSHAPE': 'hshape', 'RIGHTTRIANGLE': 'righttriangle', 'IMAGE': 'image',
            'SPRING': 'spring', 'ATTACH': 'attach', 'STRING': 'string', 'PULLEY': 'pulley',
            'BAKE': 'bake', 'SETTINGS': 'settings',
        }
        self._icons    = {}   # 36×36 아이콘
        self._icons_sm = {}   # 18×18 (기타 용도)
        for btn, fname in _icon_map.items():
            for ext in ('.png', '.jpg', '.jpeg'):
                path = fname + ext
                if os.path.exists(path):
                    try:
                        img = pygame.image.load(path).convert_alpha()
                        self._icons[btn]    = pygame.transform.smoothscale(img, (32, 32))
                        self._icons_sm[btn] = pygame.transform.smoothscale(img, (18, 18))
                    except Exception:
                        pass
                    break

        # hover 상태 추적
        self._hovered_btn = None   # 현재 마우스가 올라간 버튼 이름

        # 슬라이더 절대 Y 좌표 – draw() 실행 시 갱신되어 main.py에서 참조
        self.slider_coords = {
            'rot_y': 0, 'f_y': 0, 'm_y': 0,
            'rest_y': 0,
            'air_y': 0,
            'scale_w_y': 0,
            'scale_h_y': 0,
            'spring_k_y': 0,
            'vel_a_y': 0, 'vel_s_y': 0,
            'settings_close': None,
            'settings_tabs':  [],
            'bake_w_y': 0, 'bake_h_y': 0, 'bake_sub_y': 0, 'bake_dur_y': 0,
            'bake_btn_y1': 0, 'bake_btn_y2': 0,
            'z_minus_btn': (0,0,0,0),            # Z- 버튼 rect (x,y,w,h)
            'z_plus_btn':  (0,0,0,0),            # Z+ 버튼 rect
            'collision_btn': (0,0,0,0),          # Attach 충돌 ON/OFF 버튼 rect
        }

    # ──────────────────────────────────────────────────────────────
    def _compute_forces(self, info_obj, subs, scale, dt):
        """오브젝트에 작용하는 힘을 계산해서 dict로 반환.

        engine이 각 프레임에 누산한 값들을 사용:
          - tension_acc : 외부 연결(attach/string/pulley)에 의한 장력 합
          - spring_acc  : 스프링 복원력 합
          - int_acc     : 내부 구조 constraint에 의한 힘 합
          - normal_acc  : 접촉 충격량 기반 수직항력 합 (★ 개선)
          - stress_max  : 이번 프레임 내 최대 constraint 응력 (★ 신규)
        """
        safe_dt = max(dt, 0.001)
        s = max(scale, 1e-9)

        # substep 합산값 → 프레임 평균으로 변환
        ext_force    = getattr(info_obj, 'tension_acc', 0.0) / max(1, subs) / s
        spring_force = getattr(info_obj, 'spring_acc',  0.0) / max(1, subs) / s
        int_force    = getattr(info_obj, 'int_acc',     0.0) / max(1, subs) / s

        # ★ 수직항력: engine이 접촉 충격량 기반으로 직접 계산한 값
        #   normal_acc = Σ (m·|Δv_n| / dt) — 실제 접촉력 추정
        normal_force = getattr(info_obj, 'normal_acc', 0.0) / max(1, subs) / s

        # fallback: normal_acc가 0이면 기존 normal_offset 방식도 보조로 사용
        if normal_force < 1e-6:
            for p in info_obj.particles:
                if not p.is_static:
                    nf = p.normal_offset * p.mass * subs / (safe_dt ** 2)
                    normal_force += nf.length() / s

        # ★ 응력: constraint별로 계산된 stress_max (인장/압축 응력)
        stress = getattr(info_obj, 'stress_max', 0.0) / max(1, subs) / s

        return {
            'ext_force':    ext_force,
            'spring_force': spring_force,
            'int_force':    int_force,
            'normal_force': normal_force,
            'stress':       stress,
        }

    def _draw_weld_stitches(self, oA, oB, cam):
        """두 물체의 접합 모서리 전체를 검은 얇은 실로 촘촘히 꿰맨다(X 레이싱).
        모서리를 따라 양쪽 가장자리(레일) + 교차 스티치를 그린다."""
        import math as _m
        ptsA = [cam.to_screen(p.pos) for p in oA.particles]
        ptsB = [cam.to_screen(p.pos) for p in oB.particles]
        if not ptsA or not ptsB:
            return
        cA = (sum(x for x, _ in ptsA) / len(ptsA), sum(y for _, y in ptsA) / len(ptsA))
        cB = (sum(x for x, _ in ptsB) / len(ptsB), sum(y for _, y in ptsB) / len(ptsB))
        ax, ay = cB[0] - cA[0], cB[1] - cA[1]
        L = _m.hypot(ax, ay)
        if L < 1:
            self._draw_weld_stitch_point(cA)
            return
        axu = (ax / L, ay / L)                 # 두 물체를 잇는 방향
        sdir = (-axu[1], axu[0])               # 접합 모서리(수직) 방향

        # 가장 가까운 파티클 쌍의 중점 = 접합부 위치
        best = None; bd = None
        for pa in oA.particles:
            for pb in oB.particles:
                dd = pa.pos.distance_squared_to(pb.pos)
                if bd is None or dd < bd:
                    bd = dd; best = (pa.pos, pb.pos)
        mid = cam.to_screen((best[0] + best[1]) * 0.5)

        # 모서리 방향으로 두 물체의 투영 겹침 구간 = 공유 모서리 길이
        def _proj(pts):
            vs = [(px - mid[0]) * sdir[0] + (py - mid[1]) * sdir[1] for px, py in pts]
            return min(vs), max(vs)
        aLo, aHi = _proj(ptsA); bLo, bHi = _proj(ptsB)
        lo = max(aLo, bLo); hi = min(aHi, bHi)
        if hi - lo < 4:                        # 겹침이 거의 없으면 접합부 주변
            half = max(8, int(cam.scale(10))); lo, hi = -half, half

        depth   = max(3, int(cam.scale(5)))    # 각 물체 안쪽으로 파고드는 깊이
        spacing = max(4, int(cam.scale(5)))    # 실 간격(촘촘)
        n = max(2, int((hi - lo) / spacing))
        col = (20, 20, 20)

        def _pt(s, d):
            cx = mid[0] + sdir[0] * s; cy = mid[1] + sdir[1] * s
            return (int(cx + axu[0] * d), int(cy + axu[1] * d))

        # 양쪽 가장자리 레일(모서리선)
        railA0 = _pt(lo, -depth); railA1 = _pt(hi, -depth)
        railB0 = _pt(lo, +depth); railB1 = _pt(hi, +depth)
        pygame.draw.line(self.screen, col, railA0, railA1, 1)
        pygame.draw.line(self.screen, col, railB0, railB1, 1)

        # 교차 스티치(X 레이싱) — 모서리 전체에 촘촘히
        for k in range(n):
            s0 = lo + (hi - lo) * k / n
            s1 = lo + (hi - lo) * (k + 1) / n
            A0 = _pt(s0, -depth); B0 = _pt(s0, +depth)
            A1 = _pt(s1, -depth); B1 = _pt(s1, +depth)
            pygame.draw.line(self.screen, col, A0, B1, 1)
            pygame.draw.line(self.screen, col, B0, A1, 1)

    def _draw_weld_stitch_point(self, sc, r=None):
        """점 접합(용수철 끝점 등)에 작은 검은 실 매듭(별표형 스티치)."""
        import math as _m
        x, y = int(sc[0]), int(sc[1])
        if r is None:
            r = 5
        r = max(3, int(r))
        col = (20, 20, 20)
        for ang in (0, 45, 90, 135):
            a = _m.radians(ang)
            dx = int(_m.cos(a) * r); dy = int(_m.sin(a) * r)
            pygame.draw.line(self.screen, col, (x - dx, y - dy), (x + dx, y + dy), 1)

    def draw(self, engine, mode, drawing, draw_start_pos_world,
             mouse_world, attach_p1, weld_target, pulley_nodes,
             hinge_targets, paused, info_obj, dt, sidebar_x,
             ui_groups, cam, unit_idx, unit_scales, unit_names,
             bake_config, show_axes, show_velocity_graph,
             selected_objs=None, rbox_start=None, rbox_end=None,
             mouse_screen=None):
        if selected_objs is None: selected_objs = []

        W, H = self.screen.get_width(), self.screen.get_height()
        sidebar_w = 52   # 아이콘 전용 세로 사이드바

        # hover 감지: _btn_rects는 이전 프레임에서 만들어진 rect 사용
        self._hovered_btn = None
        if mouse_screen and sidebar_x > -sidebar_w and hasattr(self, '_btn_rects'):
            for btn, brect in self._btn_rects.items():
                if brect.collidepoint(mouse_screen):
                    self._hovered_btn = btn
                    break

        # ── 배경: Win95 회색 ──────────────────────────────────────
        self.screen.fill(C_BG)

        # ── 월드 캔버스: 흰색 + IP 스타일 sunken border ──────────
        boundary_rect = pygame.Rect(
            *cam.to_screen((0, 0)),
            int(engine.width * cam.zoom),
            int(engine.height * cam.zoom)
        )
        pygame.draw.rect(self.screen, C_CANVAS, boundary_rect)
        # Win95 sunken border (어두운 위/좌, 밝은 아래/우)
        br = boundary_rect
        pygame.draw.lines(self.screen, (64,64,64),  False,
            [(br.left,br.bottom),(br.left,br.top),(br.right,br.top)], 2)
        pygame.draw.lines(self.screen, (255,255,255), False,
            [(br.left,br.bottom),(br.right,br.bottom),(br.right,br.top)], 2)

        # ── 그리드 / 축 ───────────────────────────────────────────
        if show_axes:
            # IP 스타일: 회색 실선 격자
            grid_step = 50   # IP는 50px 단위 격자
            ww, wh = int(engine.width), int(engine.height)
            for gx in range(0, ww+1, grid_step):
                p1, p2 = cam.to_screen((gx, 0)), cam.to_screen((gx, wh))
                thick = 2 if gx % 100 == 0 else 1
                col   = (180,180,180) if gx % 100 == 0 else C_GRID
                pygame.draw.line(self.screen, col, p1, p2, thick)
            for gy in range(0, wh+1, grid_step):
                p1, p2 = cam.to_screen((0, gy)), cam.to_screen((ww, gy))
                thick = 2 if gy % 100 == 0 else 1
                col   = (180,180,180) if gy % 100 == 0 else C_GRID
                pygame.draw.line(self.screen, col, p1, p2, thick)

        # ── 오브젝트 렌더링 (z_layer 오름차순) ─────────────────────

        for obj in sorted(engine.objects, key=lambda o: getattr(o, 'z_layer', 0)):
            is_static_obj = all(p.is_static for p in obj.particles)
            center = sum((p.pos for p in obj.particles), pygame.math.Vector2()) / len(obj.particles)
            sc_center = cam.to_screen(center)

            if mode == 'WELD' and obj == weld_target:
                pygame.draw.circle(self.screen, (*C_YELLOW, 120),
                                   sc_center, int(cam.scale(48)), max(2, int(cam.scale(3))))
            if mode == 'HINGE':
                if len(hinge_targets) > 0 and obj == hinge_targets[0]:
                    pygame.draw.circle(self.screen, (*C_GREEN, 120),
                                       sc_center, int(cam.scale(48)), max(2, int(cam.scale(3))))
                if len(hinge_targets) > 1 and obj == hinge_targets[1]:
                    pygame.draw.circle(self.screen, (*C_YELLOW, 120),
                                       sc_center, int(cam.scale(48)), max(2, int(cam.scale(3))))

            if obj.image:
                angle = obj.get_angle() if hasattr(obj, 'get_angle') else 0
                if isinstance(obj, Circle) and hasattr(obj, 'update_angle'):
                    if not paused:
                        obj.update_angle()
                    angle = obj.angle
                scaled_size = (int(obj.image.get_width()*cam.zoom),
                               int(obj.image.get_height()*cam.zoom))
                rotated_img = pygame.transform.rotate(
                    pygame.transform.smoothscale(obj.image, scaled_size), -angle)
                self.screen.blit(rotated_img,
                                 rotated_img.get_rect(center=sc_center).topleft)

            elif isinstance(obj, Circle):
                ip_col = C_OBJ_SEL if (obj in selected_objs or obj == info_obj) else C_OBJ
                pygame.draw.circle(self.screen, ip_col,
                                   sc_center, int(cam.scale(obj.radius)))
                pygame.draw.circle(self.screen, (0,0,0),
                                   sc_center, int(cam.scale(obj.radius)), 1)
                if isinstance(obj, Circle) and hasattr(obj, 'update_angle') and not obj.image:
                    if not paused: obj.update_angle()

            else:
                ip_col = C_OBJ_SEL if (obj in selected_objs or obj == info_obj) else C_OBJ
                if isinstance(obj, Box):
                    pygame.draw.polygon(self.screen, ip_col,
                                        [cam.to_screen(p.pos) for p in obj.particles[:4]])
                    pygame.draw.polygon(self.screen, (0,0,0),
                                        [cam.to_screen(p.pos) for p in obj.particles[:4]], 1)
                    if obj in selected_objs or obj == info_obj:
                        pygame.draw.polygon(self.screen, C_ACCENT,
                                            [cam.to_screen(p.pos) for p in obj.particles[:4]], 2)
                elif isinstance(obj, (Triangle, RightTriangle)):
                    pygame.draw.polygon(self.screen, ip_col,
                                        [cam.to_screen(p.pos) for p in obj.particles[:3]])
                    pygame.draw.polygon(self.screen, (0,0,0),
                                        [cam.to_screen(p.pos) for p in obj.particles[:3]], 1)
                    if obj in selected_objs or obj == info_obj:
                        pygame.draw.polygon(self.screen, C_ACCENT,
                                            [cam.to_screen(p.pos) for p in obj.particles[:3]], 2)
                elif isinstance(obj, (PolygonShape, HShape, TShape, CompoundShape)):
                    box_groups = getattr(obj, 'box_groups', None)
                    if box_groups:
                        for corners in box_groups:
                            pts = [cam.to_screen(p.pos) for p in corners]
                            pygame.draw.polygon(self.screen, ip_col, pts)
                            pygame.draw.polygon(self.screen, (0,0,0), pts, 1)
                    else:
                        rp = getattr(obj, 'render_particles', obj.particles[:3])
                        pts = [cam.to_screen(p.pos) for p in rp]
                        pygame.draw.polygon(self.screen, ip_col, pts)
                        pygame.draw.polygon(self.screen, (0,0,0), pts, 1)

            for c in obj.constraints:
                if c.style == "spring":
                    draw_zigzag(self.screen, (64, 64, 64), c.p1.pos, c.p2.pos, 3, cam)
                    pygame.draw.circle(self.screen, (0,0,0),
                                       cam.to_screen(c.p1.pos), int(cam.scale(4)))
                    pygame.draw.circle(self.screen, (0,0,0),
                                       cam.to_screen(c.p2.pos), int(cam.scale(4)))
                elif isinstance(obj, StringObj):
                    pygame.draw.line(self.screen, (0, 0, 0),
                                     cam.to_screen(c.p1.pos),
                                     cam.to_screen(c.p2.pos),
                                     max(1, int(cam.scale(2))))

            if is_static_obj and not isinstance(obj, (StringObj, TrueSpring)):
                # IP 스타일 고정점 (십자 마커)
                r = int(cam.scale(8))
                pygame.draw.circle(self.screen, (200,200,200), sc_center, r)
                pygame.draw.circle(self.screen, (0,0,0), sc_center, r, 1)
                pygame.draw.line(self.screen, (0,0,0),
                    (sc_center[0]-r, sc_center[1]), (sc_center[0]+r, sc_center[1]), 1)
                pygame.draw.line(self.screen, (0,0,0),
                    (sc_center[0], sc_center[1]-r), (sc_center[0], sc_center[1]+r), 1)
            else:
                for p in obj.particles:
                    if p.is_static:
                        pygame.draw.circle(self.screen, (180,180,180),
                                           cam.to_screen(p.pos), max(3,int(cam.scale(4))))
                        pygame.draw.circle(self.screen, (0,0,0),
                                           cam.to_screen(p.pos), max(3,int(cam.scale(4))), 1)

            if mode == 'VELOCITY' and obj == info_obj and not is_static_obj:
                safe_dt = max(dt, 0.001)
                vx = sum((p.pos.x - p.old_pos.x) for p in obj.particles) / len(obj.particles) / safe_dt
                vy = sum((p.pos.y - p.old_pos.y) for p in obj.particles) / len(obj.particles) / safe_dt
                speed = math.hypot(vx, vy)
                if speed > 1:
                    scale_v = min(80, speed * 0.15)
                    nx, ny = vx/speed, vy/speed
                    ex = center.x + nx * scale_v
                    ey = center.y + ny * scale_v
                    end_sc = cam.to_screen((ex, ey))
                    # IP 스타일 화살표 (초록, 굵은 선 + 삼각 화살촉)
                    pygame.draw.line(self.screen, C_VEL_VEC, sc_center, end_sc,
                                     max(2, int(cam.scale(3))))
                    arr = max(8, int(cam.scale(10)))
                    angle = math.atan2(ny, nx)
                    for da in [2.5, -2.5]:
                        ax = ex - nx*arr*0.8 + (-ny)*math.sin(da)*arr*0.5
                        ay = ey - ny*arr*0.8 + ( nx)*math.sin(da)*arr*0.5
                        pygame.draw.line(self.screen, C_VEL_VEC,
                                         end_sc, cam.to_screen((ax,ay)),
                                         max(2, int(cam.scale(3))))
                    # "v" 레이블
                    lbl = self.icon_font.render("v", True, C_VEL_VEC)
                    self.screen.blit(lbl, (end_sc[0]+4, end_sc[1]-10))

        # ── 글로벌 제약 ───────────────────────────────────────────
        # info_obj가 AttachProxy면 해당 constraint 강조
        _selected_constraint = getattr(info_obj, 'constraint', None) if info_obj and getattr(info_obj, 'name', '') == 'Attach' else None

        # ── Weld 심볼 렌더링 ─────────────────────────────────────
        #   접합 모서리 전체를 검은 얇은 실로 촘촘히 꿰맨다(스티치 스타일).
        _weld_groups_r = {}
        for obj in engine.objects:
            wgid = getattr(obj, 'weld_group_id', None)
            if wgid is None: continue
            _weld_groups_r.setdefault(wgid, []).append(obj)

        _drawn_weld_pairs = set()
        for wgid, wobjs in _weld_groups_r.items():
            if len(wobjs) < 2: continue
            # 그룹에 용수철이 있으면 연결은 용수철 끝점 글루로 표시(아래 블록).
            if any(getattr(o, 'name', '') == 'Spring' for o in wobjs):
                continue
            for ai in range(len(wobjs)):
                for bi in range(ai + 1, len(wobjs)):
                    oA, oB = wobjs[ai], wobjs[bi]
                    if getattr(oA, 'name', '') == 'Spring' \
                       or getattr(oB, 'name', '') == 'Spring':
                        continue
                    if not oA.particles or not oB.particles:
                        continue
                    pair_key = (id(oA), id(oB))
                    if pair_key in _drawn_weld_pairs: continue
                    _drawn_weld_pairs.add(pair_key)
                    self._draw_weld_stitches(oA, oB, cam)

        # ── 용수철 weld(글루) 심볼: 용접된 '끝점'에 실 매듭 ──────────────────
        _spring_anchors = getattr(engine, '_spring_anchors', None)
        if _spring_anchors:
            _pid_to_p = {}
            for obj in engine.objects:
                for p in obj.particles:
                    _pid_to_p[id(p)] = p
            knot_r = max(3, int(cam.scale(5)))
            for ep_pid, target in _spring_anchors.items():
                ep = _pid_to_p.get(ep_pid)
                if ep is None or target not in engine.objects:
                    continue
                self._draw_weld_stitch_point(cam.to_screen(ep.pos), knot_r)

        for c in engine.global_constraints:
            if c.style == "weld":
                pass  # weld는 위에서 그룹 단위로 렌더링
            elif c.style == "hinge":
                r = int(cam.scale(7))
                pygame.draw.circle(self.screen, (200,200,200),
                                   cam.to_screen(c.p1.pos), r)
                pygame.draw.circle(self.screen, (0,0,0),
                                   cam.to_screen(c.p1.pos), r, 1)
                pygame.draw.circle(self.screen, (0,0,0),
                                   cam.to_screen(c.p1.pos), max(2,int(cam.scale(2))), 1)
            else:
                is_sel = (c is _selected_constraint)
                col = C_OBJ_SEL if is_sel else C_YELLOW
                w   = max(2, int(cam.scale(5 if is_sel else 4)))
                pygame.draw.line(self.screen, col,
                                 cam.to_screen(c.p1.pos), cam.to_screen(c.p2.pos), w)
                if is_sel:
                    # 양 끝점 원 강조
                    pygame.draw.circle(self.screen, C_OBJ_SEL,
                                       cam.to_screen(c.p1.pos), max(4, int(cam.scale(5))))
                    pygame.draw.circle(self.screen, C_OBJ_SEL,
                                       cam.to_screen(c.p2.pos), max(4, int(cam.scale(5))))

        # ── 풀리 ─────────────────────────────────────────────────
        for pc in engine.pulley_constraints:
            for i in range(len(pc.pts) - 1):
                pygame.draw.line(self.screen, (0,0,0),
                                 cam.to_screen(pc.pts[i].pos),
                                 cam.to_screen(pc.pts[i+1].pos),
                                 max(1, int(cam.scale(2))))
            for i in range(1, len(pc.pts) - 1):
                pygame.draw.circle(self.screen, (80,85,100),
                                   cam.to_screen(pc.pts[i].pos), int(cam.scale(8)))

        if mode == 'PULLEY' and pulley_nodes:
            for i in range(len(pulley_nodes) - 1):
                pygame.draw.line(self.screen, C_TEXT_DIM,
                                 cam.to_screen(pulley_nodes[i].pos),
                                 cam.to_screen(pulley_nodes[i+1].pos),
                                 max(1, int(cam.scale(2))))
            pygame.draw.line(self.screen, C_TEXT,
                             cam.to_screen(pulley_nodes[-1].pos),
                             cam.to_screen(mouse_world),
                             max(1, int(cam.scale(2))))
            for p in pulley_nodes:
                pygame.draw.circle(self.screen, C_TEXT,
                                   cam.to_screen(p.pos), int(cam.scale(5)))

        # ── 드래그 프리뷰 ─────────────────────────────────────────
        elif (drawing and draw_start_pos_world and mouse_world
              and mode not in ['SELECT','DELETE','ATTACH','WELD','HINGE','VELOCITY','BAKE','SETTINGS']):
            s_x, s_y = draw_start_pos_world
            c_x, c_y = mouse_world
            sc_s = cam.to_screen((s_x, s_y))
            sc_c = cam.to_screen((c_x, c_y))
            p_col = (*C_ACCENT, 180)

            if mode in ['BOX','TRIANGLE','RIGHTTRIANGLE','TSHAPE','HSHAPE','IMAGE']:
                w = abs(s_x - c_x); h = abs(s_y - c_y)
                sw = abs(sc_s[0]-sc_c[0]); sh = abs(sc_s[1]-sc_c[1])
                x = min(sc_s[0], sc_c[0]); y = min(sc_s[1], sc_c[1])
                if w > 0 and h > 0:
                    s = pygame.Surface((sw or 1, sh or 1), pygame.SRCALPHA)
                    if mode in ['BOX','TSHAPE','HSHAPE','IMAGE']:
                        # 사각형 계열
                        pygame.draw.rect(s, (72,130,200,40), (0,0,sw,sh))
                        pygame.draw.rect(s, (72,130,200,180), (0,0,sw,sh), 2)
                    elif mode == 'TRIANGLE':
                        # 정삼각형 (위 꼭짓점, 좌하, 우하)
                        pygame.draw.polygon(s, (72,130,200,40),
                                            [(sw//2,0),(0,sh),(sw,sh)])
                        pygame.draw.polygon(s, (72,130,200,180),
                                            [(sw//2,0),(0,sh),(sw,sh)], 2)
                    elif mode == 'RIGHTTRIANGLE':
                        # 직각삼각형 (좌상, 좌하(직각), 우하)
                        pygame.draw.polygon(s, (72,130,200,40),
                                            [(0,0),(0,sh),(sw,sh)])
                        pygame.draw.polygon(s, (72,130,200,180),
                                            [(0,0),(0,sh),(sw,sh)], 2)
                    self.screen.blit(s, (x, y))
            elif mode == 'CIRCLE':
                r = math.hypot(c_x-s_x, c_y-s_y)
                if r > 0:
                    rs = int(cam.scale(r))
                    s = pygame.Surface((rs*2+2, rs*2+2), pygame.SRCALPHA)
                    pygame.draw.circle(s, (72,130,200,40), (rs+1,rs+1), rs)
                    pygame.draw.circle(s, (72,130,200,180), (rs+1,rs+1), rs, 2)
                    self.screen.blit(s, (sc_s[0]-rs-1, sc_s[1]-rs-1))
            elif mode == 'SPRING':
                draw_zigzag(self.screen, C_ACCENT,
                            pygame.math.Vector2(s_x,s_y),
                            pygame.math.Vector2(c_x,c_y), 4, cam)
            elif mode == 'STRING':
                pygame.draw.line(self.screen, C_TEXT_DIM, sc_s, sc_c, 2)

        # ── PAUSE 배너 ────────────────────────────────────────────
        if paused and not bake_config['is_baking'] and mode != 'SETTINGS':
            bw = 380; bh = 36
            bx = W//2 - bw//2; by = 12
            pygame.draw.rect(self.screen, C_SIDEBAR, (bx,by,bw,bh))
            pygame.draw.lines(self.screen,(255,255,255),False,
                [(bx,by+bh-1),(bx,by),(bx+bw-1,by)],1)
            pygame.draw.lines(self.screen,(64,64,64),False,
                [(bx,by+bh-1),(bx+bw-1,by+bh-1),(bx+bw-1,by)],1)
            pt = self.font.render("PAUSED — Space: Resume  |  Ctrl+Z: Undo", True, C_TEXT)
            self.screen.blit(pt, pt.get_rect(center=(W//2, by+bh//2)))

        # ── BAKE 프로그레스 ───────────────────────────────────────
        if bake_config['is_baking']:
            bw = 360; bh = 28
            bx = W//2 - bw//2; by = 14
            pygame.draw.rect(self.screen, (30,30,35), (bx,by,bw,bh), border_radius=6)
            fw = int(bw * bake_config['progress'])
            if fw > 0:
                pygame.draw.rect(self.screen, C_YELLOW, (bx,by,fw,bh), border_radius=6)
            pt = self.font.render(
                f"BAKING  {int(bake_config['progress']*100)}%  —  {bake_config['frames_done']}/{bake_config['frames_total']} frames",
                True, (255,255,255))
            self.screen.blit(pt, pt.get_rect(center=(W//2, by+bh//2)))

        # ─────────────────────────────────────────────────────────
        #  사이드바
        # ─────────────────────────────────────────────────────────
        # Win95 스타일 사이드바
        pygame.draw.rect(self.screen, C_SIDEBAR, (sidebar_x, 0, sidebar_w, H))
        # raised edge (오른쪽 경계)
        pygame.draw.line(self.screen, (64,64,64),
                         (sidebar_x+sidebar_w-1, 0), (sidebar_x+sidebar_w-1, H), 1)
        pygame.draw.line(self.screen, (255,255,255),
                         (sidebar_x, 0), (sidebar_x, H), 1)

        # 토글 탭
        tab_rect = pygame.Rect(sidebar_x+sidebar_w, H//2-30, 18, 60)
        pygame.draw.rect(self.screen, (200, 204, 218), tab_rect,
                         border_top_right_radius=6, border_bottom_right_radius=6)
        arrow = "‹" if sidebar_x > -110 else "›"
        at = self.font.render(arrow, True, C_TEXT_DIM)
        self.screen.blit(at, at.get_rect(center=tab_rect.center))

        # ── 사이드바: 44×44 아이콘 세로 나열 ─────────────────────────
        if sidebar_x > -sidebar_w:
            # 버튼 수에 맞게 자동 크기 결정
            all_btns = [(b,hk) for grp,blist in ui_groups.items() for b,hk in blist]
            n_btns  = len(all_btns)
            n_seps  = len(ui_groups) - 1   # 구분선 수
            TOGGLE_H = 3 * 36 + 3 * 3 + 10  # 토글 영역 (고정 36px 유지)
            avail_h  = H - TOGGLE_H - 10   # 버튼에 쓸 수 있는 높이
            SEP = 5
            # BTN+PAD 계산: n_btns*(BTN+PAD) + n_seps*SEP <= avail_h
            raw = (avail_h - n_seps * SEP) / max(1, n_btns)
            BTN  = max(24, min(40, int(raw) - 3))  # 24~40 사이로 클램프
            PAD  = max(2, int(raw) - BTN)
            BX   = sidebar_x + (sidebar_w - BTN) // 2   # 버튼 X
            y_btn = 6
            ICON = max(16, BTN - 8)   # 아이콘 = BTN - 8px 여백

            # 그룹 구분선 색상 목록
            group_sep_colors = {
                "1. TOOLS":   None,
                "2. OBJECTS": (160,160,160),
                "3. LINKS":   (160,160,160),
                "4. EXPORT":  (160,160,160),
                "5. SYSTEM":  (160,160,160),
            }

            # 모든 버튼 세로 나열
            self._btn_rects = {}   # btn → screen Rect (hover/click 감지용)
            for group, buttons in ui_groups.items():
                # 그룹 구분선 (첫 그룹 제외)
                sep_col = group_sep_colors.get(group)
                if sep_col and y_btn > 6:
                    pygame.draw.line(self.screen, (160,160,160),
                                     (BX+2, y_btn+1), (BX+BTN-2, y_btn+1), 1)
                    y_btn += SEP

                for btn, hotkey in buttons:
                    brect = pygame.Rect(BX, y_btn, BTN, BTN)
                    self._btn_rects[btn] = brect
                    is_active  = (mode == btn)
                    is_hovered = (self._hovered_btn == btn)

                    # 배경
                    if is_active:
                        # pressed (inset)
                        pygame.draw.rect(self.screen, (0, 0, 128), brect)
                        pygame.draw.lines(self.screen, (64,64,64), False,
                            [(brect.left,brect.bottom-1),(brect.left,brect.top),(brect.right-1,brect.top)], 1)
                        pygame.draw.lines(self.screen, (180,180,220), False,
                            [(brect.left,brect.bottom-1),(brect.right-1,brect.bottom-1),(brect.right-1,brect.top)], 1)
                    elif is_hovered:
                        # hover: raised 강조
                        pygame.draw.rect(self.screen, (230,228,220), brect)
                        pygame.draw.lines(self.screen, (255,255,255), False,
                            [(brect.left,brect.bottom-1),(brect.left,brect.top),(brect.right-1,brect.top)], 2)
                        pygame.draw.lines(self.screen, (80,80,80), False,
                            [(brect.left,brect.bottom-1),(brect.right-1,brect.bottom-1),(brect.right-1,brect.top)], 2)
                    else:
                        # normal raised
                        pygame.draw.rect(self.screen, C_SIDEBAR_B, brect)
                        pygame.draw.lines(self.screen, (255,255,255), False,
                            [(brect.left,brect.bottom-1),(brect.left,brect.top),(brect.right-1,brect.top)], 1)
                        pygame.draw.lines(self.screen, (64,64,64), False,
                            [(brect.left,brect.bottom-1),(brect.right-1,brect.bottom-1),(brect.right-1,brect.top)], 1)

                    # 아이콘 렌더링
                    icon = self._icons.get(btn)
                    if icon:
                        # 30×30으로 스케일
                        ico = pygame.transform.smoothscale(icon, (ICON, ICON))
                        if is_active:
                            # 활성: 흰색 틴트
                            white = pygame.Surface((ICON, ICON), pygame.SRCALPHA)
                            white.fill((255,255,255,60))
                            ico.blit(white, (0,0))
                        elif btn == 'DELETE':
                            # 빨간색 틴트
                            red = pygame.Surface((ICON, ICON), pygame.SRCALPHA)
                            red.fill((200,50,50,80))
                            ico.blit(red, (0,0))
                        self.screen.blit(ico, ico.get_rect(center=brect.center))
                    else:
                        # 아이콘 없으면 단축키 텍스트
                        tc = (255,255,255) if is_active else C_TEXT
                        short = btn[:2] if len(btn)>2 else btn
                        t = self.font.render(short, True, tc)
                        self.screen.blit(t, t.get_rect(center=brect.center))

                    y_btn += BTN + PAD

            # 하단 토글 아이콘들 (하단 3개: GRAVITY / GRID / UNIT)
            toggle_data = [
                ("G", engine.gravity_enabled, (0,0,128),   "GRAVITY"),
                ("▦", show_axes,              (0,100,0),   "GRID"),
                (unit_names[unit_idx][0] if unit_names else "m",
                 True, (80,80,80), unit_names[unit_idx] if unit_names else "m"),
            ]
            T_BTN = 36; T_PAD = 3   # 토글은 고정 크기
            ty = H - len(toggle_data) * (T_BTN + T_PAD) - 8
            self._toggle_rects = []
            TBX = sidebar_x + (sidebar_w - T_BTN) // 2
            for sym, active, on_col, tlbl in toggle_data:
                trect = pygame.Rect(TBX, ty, T_BTN, T_BTN)
                self._toggle_rects.append((trect, active, tlbl))
                if active:
                    pygame.draw.rect(self.screen, on_col, trect)
                    pygame.draw.lines(self.screen,(64,64,64),False,
                        [(trect.left,trect.bottom-1),(trect.left,trect.top),(trect.right-1,trect.top)],1)
                    tc = (255,255,255)
                else:
                    pygame.draw.rect(self.screen, C_SIDEBAR_B, trect)
                    pygame.draw.lines(self.screen,(255,255,255),False,
                        [(trect.left,trect.bottom-1),(trect.left,trect.top),(trect.right-1,trect.top)],1)
                    pygame.draw.lines(self.screen,(64,64,64),False,
                        [(trect.left,trect.bottom-1),(trect.right-1,trect.bottom-1),(trect.right-1,trect.top)],1)
                    tc = C_TEXT
                ts = self.title_font.render(sym, True, tc)
                self.screen.blit(ts, ts.get_rect(center=trect.center))
                ty += T_BTN + T_PAD

            # hover 툴팁 (버튼 오른쪽에 말풍선)
            if self._hovered_btn:
                tip_names = {
                    'SELECT':'Select', 'WELD':'Weld', 'HINGE':'Hinge',
                    'VELOCITY':'Velocity', 'DELETE':'Delete',
                    'CIRCLE':'Circle', 'BOX':'Box', 'TRIANGLE':'Triangle',
                    'TSHAPE':'T-Shape', 'HSHAPE':'H-Shape', 'RIGHTTRIANGLE':'Right Triangle',
                    'IMAGE':'Image', 'SPRING':'Spring', 'ATTACH':'Attach',
                    'STRING':'String', 'PULLEY':'Pulley', 'BAKE':'Export',
                    'PIN':'Pin',
                }
                hbtn = self._hovered_btn
                tip_label = tip_names.get(hbtn, hbtn)
                # 단축키도 표시
                hotkey_str = ""
                for grp, btns in ui_groups.items():
                    for b, hk in btns:
                        if b == hbtn: hotkey_str = hk; break
                if hotkey_str:
                    tip_label += f"  [{hotkey_str}]"

                tip_surf  = self.font.render(tip_label, True, (0,0,0))
                tip_w     = tip_surf.get_width() + 16
                tip_h     = tip_surf.get_height() + 8
                # 버튼 오른쪽에 말풍선
                hbrect = self._btn_rects.get(hbtn)
                if hbrect:
                    tx = sidebar_x + sidebar_w + 6
                    ty2 = hbrect.centery - tip_h // 2
                    ty2 = max(2, min(H - tip_h - 2, ty2))
                    # 노란 Win95 툴팁 배경
                    pygame.draw.rect(self.screen, (255,255,225), (tx, ty2, tip_w, tip_h))
                    pygame.draw.rect(self.screen, (0,0,0), (tx, ty2, tip_w, tip_h), 1)
                    # 작은 삼각형 화살표 (왼쪽)
                    mid_y = ty2 + tip_h // 2
                    pygame.draw.polygon(self.screen, (255,255,225),
                                        [(tx,   mid_y-4),(tx,   mid_y+4),(tx-6, mid_y)])
                    pygame.draw.lines(self.screen, (0,0,0), False,
                                      [(tx-6, mid_y),(tx, mid_y-4)], 1)
                    pygame.draw.lines(self.screen, (0,0,0), False,
                                      [(tx-6, mid_y),(tx, mid_y+4)], 1)
                    self.screen.blit(tip_surf, (tx+8, ty2+4))

        # ─────────────────────────────────────────────────────────
        #  우측 패널 – BAKE
        # ─────────────────────────────────────────────────────────
        panel_w = 270
        panel_x = W - panel_w - 16

        if mode == 'BAKE':
            panel_h = 350
            panel_y = 16
            # Win95 dialog
            pygame.draw.rect(self.screen, C_SIDEBAR, (panel_x, panel_y, panel_w, panel_h))
            pygame.draw.lines(self.screen,(255,255,255),False,
                [(panel_x,panel_y+panel_h-1),(panel_x,panel_y),(panel_x+panel_w-1,panel_y)],2)
            pygame.draw.lines(self.screen,(64,64,64),False,
                [(panel_x,panel_y+panel_h-1),(panel_x+panel_w-1,panel_y+panel_h-1),(panel_x+panel_w-1,panel_y)],2)
            # 타이틀바
            tb = pygame.Rect(panel_x+2, panel_y+2, panel_w-4, 18)
            pygame.draw.rect(self.screen, (0,0,128), tb)
            ht = self.font.render("  EXPORT / WORLD SETTINGS", True, (255,255,255))
            self.screen.blit(ht, (tb.x+2, tb.y+2))

            px, py = panel_x+10, panel_y+26
            sw = panel_w - 20

            def bake_slider(label, val_str, ratio, abs_py):
                track_y = abs_py + 16
                self.screen.blit(self.title_font.render(label, True, C_TEXT_DIM), (px, abs_py))
                vt = self.font.render(val_str, True, C_TEXT)
                self.screen.blit(vt, (px+sw-vt.get_width(), abs_py))
                # Win95 trackbar
                pygame.draw.rect(self.screen, (128,128,128), (px, track_y, sw, 4))
                pygame.draw.rect(self.screen, (255,255,255), (px, track_y+2, sw, 2))
                if ratio > 0:
                    pygame.draw.rect(self.screen, (0,0,128), (px, track_y, int(ratio*sw), 4))
                hx = int(px+ratio*sw)
                pygame.draw.rect(self.screen, C_SIDEBAR_B, (hx-5, track_y-6, 10, 16))
                pygame.draw.lines(self.screen,(255,255,255),False,[(hx-5,track_y+9),(hx-5,track_y-6),(hx+4,track_y-6)],1)
                pygame.draw.lines(self.screen,(64,64,64),False,[(hx-5,track_y+9),(hx+4,track_y+9),(hx+4,track_y-6)],1)
                return track_y + 3  # 핸들 중심 절대 y

            r1 = (bake_config['world_w']-1000)/9000.0
            self.slider_coords['bake_w_y'] = bake_slider("World Width", f"{int(bake_config['world_w'])} px", r1, py); py += 40

            r2 = (bake_config['world_h']-1000)/9000.0
            self.slider_coords['bake_h_y'] = bake_slider("World Height", f"{int(bake_config['world_h'])} px", r2, py); py += 40

            r3 = (bake_config['substeps']-1)/99.0
            self.slider_coords['bake_sub_y'] = bake_slider("Physics Sub-steps", f"{int(bake_config['substeps'])}×", r3, py); py += 40

            r4 = (bake_config['bake_time']-1)/59.0
            self.slider_coords['bake_dur_y'] = bake_slider("Video Duration", f"{int(bake_config['bake_time'])} sec", r4, py); py += 52

            btn = pygame.Rect(px, py, sw, 38)
            self.slider_coords['bake_btn_y1'] = py
            self.slider_coords['bake_btn_y2'] = py + 38
            bc = (200,80,80) if not bake_config['is_baking'] else (60,65,80)
            pygame.draw.rect(self.screen, bc, btn, border_radius=8)
            bt = self.font.render(
                "▶  START BAKING (MP4)" if not bake_config['is_baking'] else "⏳ BAKING...",
                True, (255,255,255))
            self.screen.blit(bt, bt.get_rect(center=btn.center))

        # ─────────────────────────────────────────────────────────
        #  우측 패널 – Object Info
        # ─────────────────────────────────────────────────────────
        elif info_obj:
            scale  = unit_scales[unit_idx]
            u_name = unit_names[unit_idx]
            subs   = max(1, int(bake_config.get('substeps', 10)))

            cx = sum(p.pos.x for p in info_obj.particles) / len(info_obj.particles)
            cy = sum(p.pos.y for p in info_obj.particles) / len(info_obj.particles)
            vx = sum((p.pos.x - p.old_pos.x) for p in info_obj.particles) / len(info_obj.particles) / max(dt, 0.001)
            vy = sum((p.pos.y - p.old_pos.y) for p in info_obj.particles) / len(info_obj.particles) / max(dt, 0.001)
            speed_val = math.hypot(vx, vy) / scale
            v_angle   = math.degrees(math.atan2(vy, vx)) % 360
            obj_angle = info_obj.get_angle() if hasattr(info_obj, 'get_angle') else 0
            is_static_flag = all(p.is_static for p in info_obj.particles)

            cp = self._compute_forces(info_obj, subs, scale, dt)
            ext_force    = cp['ext_force']
            int_force    = cp['int_force']
            normal_force = cp['normal_force']
            spring_force = cp.get('spring_force', 0.0)
            stress_val   = cp.get('stress', 0.0)
            f_unit = "N" if u_name == 'm' else (f"kg·{u_name}/s²")

            is_vel_mode = (mode == 'VELOCITY')
            from objects import TrueSpring as _TSp
            _is_spring_sel = isinstance(info_obj, _TSp)

            # ── 패널 크기 자동 결정 ──────────────────────────────
            PANEL_W = 260
            PANEL_X = W - PANEL_W - 12
            PANEL_Y = 16
            _base_h = 760 if is_vel_mode else 660
            if _is_spring_sel: _base_h += 36   # 스프링 k 슬라이더 공간
            PANEL_H = min(H - PANEL_Y - 12, _base_h)

            # Win95 raised dialog 배경
            pygame.draw.rect(self.screen, C_SIDEBAR, (PANEL_X, PANEL_Y, PANEL_W, PANEL_H))
            pygame.draw.lines(self.screen, (255,255,255), False,
                [(PANEL_X, PANEL_Y+PANEL_H-1),(PANEL_X, PANEL_Y),(PANEL_X+PANEL_W-1, PANEL_Y)], 2)
            pygame.draw.lines(self.screen, (64,64,64), False,
                [(PANEL_X, PANEL_Y+PANEL_H-1),(PANEL_X+PANEL_W-1, PANEL_Y+PANEL_H-1),(PANEL_X+PANEL_W-1, PANEL_Y)], 2)

            px2 = PANEL_X + 8
            sw2 = PANEL_W - 16
            py2 = PANEL_Y + 4

            # ── 타이틀바 ─────────────────────────────────────────
            title_rect = pygame.Rect(PANEL_X+2, PANEL_Y+2, PANEL_W-4, 18)
            pygame.draw.rect(self.screen, (0,0,128), title_rect)
            icon_ch = {"Circle":"●","Box":"■","Triangle":"▲","Spring":"~",
                       "String":"―","HShape":"H","TShape":"T","RightTriangle":"◥",
                       "ImageBlock":"🖼","Attach":"⬡"}.get(info_obj.name, "◆")
            ht = self.font.render(f"  {icon_ch}  {info_obj.name}", True, (255,255,255))
            self.screen.blit(ht, (title_rect.x+2, title_rect.y+2))
            py2 = PANEL_Y + 26

            # ────────────────────────────────────────────────────
            def _sep(label=None):
                nonlocal py2
                pygame.draw.line(self.screen, (128,128,128), (px2, py2), (px2+sw2, py2))
                pygame.draw.line(self.screen, (255,255,255), (px2, py2+1), (px2+sw2, py2+1))
                py2 += 3
                if label:
                    ls = self.title_font.render(label, True, C_TEXT_DIM)
                    lb_bg = pygame.Surface((ls.get_width()+6, ls.get_height()+2))
                    lb_bg.fill(C_SIDEBAR); lb_bg.blit(ls, (3,1))
                    self.screen.blit(lb_bg, (px2+4, py2-1))
                    py2 += 13

            def _row(label, value, vc=None):
                nonlocal py2
                ls = self.title_font.render(label, True, C_TEXT_DIM)
                vs = self.font.render(str(value), True, vc or C_TEXT)
                self.screen.blit(ls, (px2, py2))
                self.screen.blit(vs, (px2+sw2-vs.get_width(), py2))
                py2 += 15

            # ── POSITION / VELOCITY ───────────────────────────
            _sep("STATE")
            _row("Position", f"({cx/scale:.1f}, {cy/scale:.1f}) {u_name}", C_GREEN)
            _row("Velocity",  f"({vx/scale:.1f}, {vy/scale:.1f}) {u_name}/s")
            _row("Speed",     f"{speed_val:.2f} {u_name}/s  ∠{int(v_angle)}°")
            _row("Static",    "YES" if is_static_flag else "no")
            py2 += 2

            # ── FORCES ───────────────────────────────────────
            _sep("FORCES")
            _row("Normal (N)",        f"{normal_force:.2f} {f_unit}",  (0,120,0))
            _row("Tension",           f"{ext_force:.2f} {f_unit}",     C_FORCE_VEC)
            _row("Spring",            f"{spring_force:.2f} {f_unit}",  (0,80,200))
            _row("Internal Stress",   f"{int_force:.2f} {f_unit}",     (140,90,0))
            _row("Peak Stress",       f"{stress_val:.2f} {f_unit}",    (180,60,60))
            py2 += 2

            # ── PROPERTIES 슬라이더 ─────────────────────────────
            _sep("PROPERTIES  (drag · right-click)")

            r_rot  = (obj_angle % 360) / 360.0
            self.slider_coords['rot_y'] = _win95_trackbar(
                self.screen, px2, py2, sw2, r_rot,
                "Rotation", f"{int(obj_angle)%360}°", self.title_font)
            py2 += 30

            r_fric = min(1.0, info_obj.friction / 0.1)
            self.slider_coords['f_y'] = _win95_trackbar(
                self.screen, px2, py2, sw2, r_fric,
                "Friction μ", f"{info_obj.friction*100:.1f}%", self.title_font)
            py2 += 30

            r_mass = max(0.0, min(1.0, (info_obj.mass-0.1)/49.9))
            self.slider_coords['m_y'] = _win95_trackbar(
                self.screen, px2, py2, sw2, r_mass,
                "Mass", f"{info_obj.mass:.1f} kg", self.title_font)
            py2 += 30

            rest_val = getattr(info_obj, 'restitution', 0.5)
            self.slider_coords['rest_y'] = _win95_trackbar(
                self.screen, px2, py2, sw2, max(0.0, min(1.0, rest_val)),
                "Restitution e", f"{rest_val:.2f}", self.title_font, (0,80,160))
            py2 += 30

            air_val = getattr(info_obj, 'air_drag', 0.0)
            self.slider_coords['air_y'] = _win95_trackbar(
                self.screen, px2, py2, sw2, max(0.0, min(1.0, air_val)),
                "Air Drag", f"{air_val*100:.0f}%", self.title_font, (0,100,140))
            py2 += 30

            # ── SCALE (크기 조절) ────────────────────────────────
            _sep("SIZE")
            from objects import Circle as _Circ
            _is_circ = isinstance(info_obj, _Circ)
            if hasattr(info_obj, 'get_size'):
                _sw_sz, _sh_sz = info_obj.get_size()
                if _is_circ:
                    # Circle: radius 기준으로 슬라이더 표시/적용
                    # get_size() = (radius*2, radius*2) 이므로 radius = _sw_sz/2
                    _r_val  = info_obj.radius          # 실제 반지름
                    MAX_R   = 400.0                    # 슬라이더 최대 반지름
                    _ratio_r = max(0.0, min(1.0, _r_val / MAX_R))
                    self.slider_coords['scale_w_y'] = _win95_trackbar(
                        self.screen, px2, py2, sw2,
                        _ratio_r,
                        "Radius", f"{_r_val:.0f} px", self.title_font, (60,120,40))
                    py2 += 30
                    self.slider_coords['scale_h_y'] = 0
                else:
                    self.slider_coords['scale_w_y'] = _win95_trackbar(
                        self.screen, px2, py2, sw2,
                        max(0.0, min(1.0, _sw_sz / 800.0)),
                        "Width", f"{_sw_sz:.0f} px", self.title_font, (60,120,40))
                    py2 += 30
                    self.slider_coords['scale_h_y'] = _win95_trackbar(
                        self.screen, px2, py2, sw2,
                        max(0.0, min(1.0, _sh_sz / 800.0)),
                        "Height", f"{_sh_sz:.0f} px", self.title_font, (60,120,40))
                    py2 += 30
            else:
                self.slider_coords['scale_w_y'] = 0
                self.slider_coords['scale_h_y'] = 0

            # ── SPRING (탄성계수 k) ──────────────────────────────
            # Spring 오브젝트일 때만 표시. k_eff = stiffness · 2e4 (engine과 일치)
            from objects import TrueSpring as _TSpring
            if isinstance(info_obj, _TSpring) and info_obj.constraints:
                _sep("SPRING")
                _stiff = getattr(info_obj.constraints[0], 'stiffness', 0.001)
                _k_eff = _stiff * 2e4
                # 로그 매핑: stiffness 0.0001(부드러움) ~ 0.05(단단함)
                K_MIN, K_MAX = 0.0001, 0.05
                import math as _m
                _r_k = (_m.log10(max(_stiff, K_MIN) / K_MIN) /
                        _m.log10(K_MAX / K_MIN))
                _r_k = max(0.0, min(1.0, _r_k))
                self.slider_coords['spring_k_y'] = _win95_trackbar(
                    self.screen, px2, py2, sw2, _r_k,
                    "Spring Const k", f"{_k_eff:.0f} N/m", self.title_font, (150,60,150))
                py2 += 30
            else:
                self.slider_coords['spring_k_y'] = 0

            # ── Z-LAYER  (Win95 스타일) ───────────────────────────
            _sep("Z-LAYER")
            z_val = getattr(info_obj, 'z_layer', 0)

            layer_colors = [
                (160, 60, 60),   # 0  레드
                (50, 100, 170),  # 1  블루
                (50, 140, 80),   # 2  그린
                (150, 110, 30),  # 3  옐로우
                (110, 60, 160),  # 4  퍼플
            ]
            lc = layer_colors[abs(z_val) % len(layer_colors)]

            BTN_W = 22; BTN_H = 18
            # [-] 버튼 (raised, 왼쪽)
            zm_rect = pygame.Rect(px2, py2, BTN_W, BTN_H)
            pygame.draw.rect(self.screen, C_SIDEBAR_B, zm_rect)
            pygame.draw.lines(self.screen, (255,255,255), False,
                [(zm_rect.left, zm_rect.bottom-1),(zm_rect.left, zm_rect.top),(zm_rect.right-1, zm_rect.top)], 1)
            pygame.draw.lines(self.screen, (64,64,64), False,
                [(zm_rect.left, zm_rect.bottom-1),(zm_rect.right-1, zm_rect.bottom-1),(zm_rect.right-1, zm_rect.top)], 1)
            zm_lbl = self.title_font.render("−", True, C_TEXT)
            self.screen.blit(zm_lbl, zm_lbl.get_rect(center=zm_rect.center))

            # [+] 버튼 (raised, 오른쪽)
            zp_rect = pygame.Rect(px2 + sw2 - BTN_W, py2, BTN_W, BTN_H)
            pygame.draw.rect(self.screen, C_SIDEBAR_B, zp_rect)
            pygame.draw.lines(self.screen, (255,255,255), False,
                [(zp_rect.left, zp_rect.bottom-1),(zp_rect.left, zp_rect.top),(zp_rect.right-1, zp_rect.top)], 1)
            pygame.draw.lines(self.screen, (64,64,64), False,
                [(zp_rect.left, zp_rect.bottom-1),(zp_rect.right-1, zp_rect.bottom-1),(zp_rect.right-1, zp_rect.top)], 1)
            zp_lbl = self.title_font.render("+", True, C_TEXT)
            self.screen.blit(zp_lbl, zp_lbl.get_rect(center=zp_rect.center))

            # 가운데 sunken 표시창
            mid_x  = px2 + BTN_W + 3
            mid_w  = sw2 - BTN_W * 2 - 6
            mid_rect = pygame.Rect(mid_x, py2, mid_w, BTN_H)
            # sunken 효과 (어두운 위/좌, 밝은 아래/우)
            pygame.draw.rect(self.screen, lc, mid_rect)
            pygame.draw.lines(self.screen, (64,64,64), False,
                [(mid_rect.left, mid_rect.bottom-1),(mid_rect.left, mid_rect.top),(mid_rect.right-1, mid_rect.top)], 1)
            pygame.draw.lines(self.screen, (255,255,255), False,
                [(mid_rect.left, mid_rect.bottom-1),(mid_rect.right-1, mid_rect.bottom-1),(mid_rect.right-1, mid_rect.top)], 1)
            # 레이어 번호 텍스트
            z_txt = self.title_font.render(f"Layer  {z_val}", True, (255,255,255))
            self.screen.blit(z_txt, z_txt.get_rect(center=mid_rect.center))

            self.slider_coords['z_minus_btn'] = (zm_rect.x, zm_rect.y, BTN_W, BTN_H)
            self.slider_coords['z_plus_btn']  = (zp_rect.x, zp_rect.y, BTN_W, BTN_H)
            py2 += BTN_H + 6

            # ── ATTACH 전용: 물체 충돌 ON/OFF 버튼 ─────────────────
            # info_obj가 AttachProxy일 때만 표시
            if getattr(info_obj, 'name', '') == 'Attach':
                _sep("COLLISION")
                _c = info_obj.constraint
                _no_col = getattr(_c, 'no_collision', False)
                _col_on  = not _no_col   # 충돌 켜진 상태

                # 버튼 전체 너비
                cbtn_rect = pygame.Rect(px2, py2, sw2, 20)
                # ON 반쪽
                on_rect  = pygame.Rect(px2,              py2, sw2 // 2, 20)
                # OFF 반쪽
                off_rect = pygame.Rect(px2 + sw2 // 2,  py2, sw2 - sw2 // 2, 20)

                for is_on, rect, label in ((True, on_rect, "  ON"), (False, off_rect, " OFF")):
                    selected = (_col_on == is_on)
                    if selected:
                        # pressed (inset) — 선택된 쪽
                        bg = (0, 100, 0) if is_on else (140, 40, 40)
                        pygame.draw.rect(self.screen, bg, rect)
                        pygame.draw.lines(self.screen, (40, 40, 40), False,
                            [(rect.left, rect.bottom-1),(rect.left, rect.top),(rect.right-1, rect.top)], 1)
                        pygame.draw.lines(self.screen, (180, 220, 180) if is_on else (220, 160, 160), False,
                            [(rect.left, rect.bottom-1),(rect.right-1, rect.bottom-1),(rect.right-1, rect.top)], 1)
                        tc = (255, 255, 255)
                    else:
                        # raised — 비선택 쪽
                        pygame.draw.rect(self.screen, C_SIDEBAR_B, rect)
                        pygame.draw.lines(self.screen, (255, 255, 255), False,
                            [(rect.left, rect.bottom-1),(rect.left, rect.top),(rect.right-1, rect.top)], 1)
                        pygame.draw.lines(self.screen, (64, 64, 64), False,
                            [(rect.left, rect.bottom-1),(rect.right-1, rect.bottom-1),(rect.right-1, rect.top)], 1)
                        tc = C_TEXT_DIM

                    lt = self.title_font.render(label, True, tc)
                    self.screen.blit(lt, lt.get_rect(center=rect.center))

                # 버튼 전체 영역을 slider_coords에 등록 (클릭 판별용)
                self.slider_coords['collision_btn'] = (cbtn_rect.x, cbtn_rect.y, cbtn_rect.w, cbtn_rect.h)
                py2 += 26
            else:
                self.slider_coords['collision_btn'] = (0, 0, 0, 0)

            # ── VELOCITY 모드: 속도 슬라이더 ────────────────────
            if is_vel_mode:
                _sep("SET VELOCITY")
                r_ang = v_angle / 360.0
                self.slider_coords['vel_a_y'] = _win95_trackbar(
                    self.screen, px2, py2, sw2, r_ang,
                    "Direction", f"{int(v_angle)}°", self.title_font, (0,128,0))
                py2 += 30
                max_speed_px = 2000.0
                r_spd = max(0.0, min(1.0, (speed_val*scale)/max_speed_px))
                self.slider_coords['vel_s_y'] = _win95_trackbar(
                    self.screen, px2, py2, sw2, r_spd,
                    "Speed", f"{speed_val:.1f} {u_name}/s", self.title_font, (0,128,0))
                py2 += 30

            # ── 힘 벡터 화살표 (캔버스 위에) ──────────────────────
            # 속도 화살표
            if mode == 'VELOCITY' and not is_static_flag:
                speed_px = math.hypot(vx, vy)
                if speed_px > 1:
                    scale_v = min(80, speed_px * 0.15)
                    nx2, ny2 = vx/speed_px, vy/speed_px
                    ex = cx + nx2 * scale_v
                    ey = cy + ny2 * scale_v
                    end_sc = cam.to_screen((ex, ey))
                    pygame.draw.line(self.screen, C_VEL_VEC, cam.to_screen((cx,cy)), end_sc,
                                     max(2, int(cam.scale(3))))
                    arr = max(8, int(cam.scale(10)))
                    for da in [2.5, -2.5]:
                        ax = ex - nx2*arr*0.8 + (-ny2)*math.sin(da)*arr*0.5
                        ay = ey - ny2*arr*0.8 + ( nx2)*math.sin(da)*arr*0.5
                        pygame.draw.line(self.screen, C_VEL_VEC,
                                         end_sc, cam.to_screen((ax,ay)),
                                         max(2, int(cam.scale(3))))
                    lbl = self.icon_font.render("v", True, C_VEL_VEC)
                    self.screen.blit(lbl, (end_sc[0]+4, end_sc[1]-10))

            # 속도 그래프
            if show_velocity_graph:
                info_obj.speed_history = getattr(info_obj, 'speed_history', [])
                info_obj.speed_history.append(speed_val)
                if len(info_obj.speed_history) > 120: info_obj.speed_history.pop(0)
                gw, gh = 200, 80
                gx = PANEL_X - gw - 8
                gy = PANEL_Y
                pygame.draw.rect(self.screen, (255,255,255), (gx,gy,gw,gh))
                pygame.draw.lines(self.screen,(64,64,64),False,
                    [(gx,gy+gh-1),(gx,gy),(gx+gw-1,gy)],1)
                pygame.draw.lines(self.screen,(255,255,255),False,
                    [(gx,gy+gh-1),(gx+gw-1,gy+gh-1),(gx+gw-1,gy)],1)
                sh = info_obj.speed_history
                if sh:
                    max_s = max(max(sh), 1)
                    pts = [(gx+12+int(i*(gw-24)/(max(len(sh)-1,1))),
                            gy+gh-8-int(v/max_s*(gh-16)))
                           for i,v in enumerate(sh)]
                    if len(pts) >= 2:
                        pygame.draw.lines(self.screen, C_FORCE_VEC, False, pts, 2)
                    gt = self.title_font.render(f"Speed  max={max_s:.1f}", True, C_TEXT_DIM)
                    self.screen.blit(gt, (gx+4, gy+2))


        # ─────────────────────────────────────────────────────────
        #  오브젝트 목록
        # ─────────────────────────────────────────────────────────
        if mode not in ['BAKE', 'SETTINGS']:
            # Attach 막대 목록 수집
            attach_proxies = []
            for c in engine.global_constraints:
                if getattr(c, 'style', 'line') not in ('weld', 'hinge') and \
                   getattr(c, 'is_solid', False):
                    attach_proxies.append(c)

            max_disp  = 15
            all_items = list(engine.objects) + attach_proxies          # 오브젝트 + attach 막대
            disp_items = all_items[-max_disp:]
            list_w = 190
            list_h = 36 + len(disp_items) * 20
            if not disp_items: list_h = 56
            list_x = W - list_w - 16
            list_y = H - list_h - 16

            # 패널과 겹치면 내림
            if info_obj and mode not in ['BAKE']:
                list_y = min(list_y, H - list_h - 16)

            # Win95 listbox
            pygame.draw.rect(self.screen, (255,255,255), (list_x,list_y,list_w,list_h))
            pygame.draw.lines(self.screen,(64,64,64),False,
                [(list_x,list_y+list_h-1),(list_x,list_y),(list_x+list_w-1,list_y)],1)
            pygame.draw.lines(self.screen,(255,255,255),False,
                [(list_x,list_y+list_h-1),(list_x+list_w-1,list_y+list_h-1),(list_x+list_w-1,list_y)],1)

            self.screen.blit(
                self.title_font.render(f"Objects  ({len(engine.objects)})  Attach ({len(attach_proxies)})", True, C_TEXT_DIM),
                (list_x+12, list_y+10))

            ty2 = list_y + 32
            # AttachProxy일 때 연결된 양쪽 오브젝트를 선택으로 표시
            _attach_sel_ids = set()
            if info_obj and getattr(info_obj, 'name', '') == 'Attach':
                c_ = getattr(info_obj, 'constraint', None)
                if c_:
                    if getattr(c_.p1, 'parent', None): _attach_sel_ids.add(id(c_.p1.parent))
                    if getattr(c_.p2, 'parent', None): _attach_sel_ids.add(id(c_.p2.parent))
            if not disp_items:
                self.screen.blit(
                    self.title_font.render("No objects yet", True, C_TEXT_DIM),
                    (list_x+12, ty2))
            else:
                start_idx = len(all_items) - len(disp_items)
                for i, item in enumerate(disp_items):
                    is_attach_c = not hasattr(item, 'particles')  # Constraint면 attach 막대
                    if is_attach_c:
                        # attach 막대 항목
                        is_sel = (info_obj and getattr(info_obj, 'name', '') == 'Attach'
                                  and getattr(info_obj, 'constraint', None) is item)
                        if is_sel:
                            pygame.draw.rect(self.screen, (0,0,128), (list_x+2,ty2-1,list_w-4,16))
                        col = (255,255,255) if is_sel else (180, 150, 0)
                        label = f"[A] Attach"
                        self.screen.blit(
                            self.title_font.render(label, True, col),
                            (list_x+12, ty2))
                    else:
                        o = item
                        is_sel = (o == info_obj) or (id(o) in _attach_sel_ids)
                        if is_sel:
                            pygame.draw.rect(self.screen, (0,0,128), (list_x+2,ty2-1,list_w-4,16))
                        col = (255,255,255) if is_sel else C_TEXT
                        z_val = getattr(o, 'z_layer', 0)
                        layer_colors = [(200,90,90),(90,160,200),(90,190,120),(190,150,80),(150,90,190)]
                        lc = layer_colors[z_val % len(layer_colors)]
                        pygame.draw.rect(self.screen, lc,
                                         (list_x + list_w - 28, ty2 + 1, 20, 14), border_radius=3)
                        zl_t = self.title_font.render(str(z_val), True, (255,255,255))
                        self.screen.blit(zl_t, zl_t.get_rect(center=(list_x+list_w-18, ty2+8)))
                        self.screen.blit(
                            self.title_font.render(f"[{start_idx+i}] {o.name}", True, col),
                            (list_x+12, ty2))
                    ty2 += 20

        # ─────────────────────────────────────────────────────────
        #  툴팁 / 상태 메시지
        # ─────────────────────────────────────────────────────────
        tip_map = {
            'WELD':     "WELD: Click two overlapping objects to merge",
            'HINGE':    f"HINGE: [1] Base object → [2] Target object → [3] Pin location  (selected: {len(hinge_targets)}/2)",
            'DELETE':   "DELETE: Click an object to remove it",
            'PULLEY':   f"PULLEY: Add nodes by clicking, press Enter to finalize  ({len(pulley_nodes)} nodes)",
            'VELOCITY': "VELOCITY: Pause simulation first (Space), then drag sliders",
            'BAKE':     "BAKE: Export a high-quality MP4  (right-click sliders for exact input)",
            'SETTINGS': "SETTINGS: Keyboard shortcuts overview  (click anywhere to close)",
            'ATTACH':   "ATTACH: Click two points to connect with a rigid link",
        }
        tip = tip_map.get(mode, "Space: Pause  |  Ctrl+Z: Undo  |  Tab: Sidebar  |  Scroll: Zoom  |  MMB Drag: Pan")

        tip_x = max(sidebar_x + sidebar_w + 16, 16)
        tip_surf = self.title_font.render(tip, True, C_TEXT_DIM)
        ts_bg = pygame.Surface((tip_surf.get_width()+16, tip_surf.get_height()+8), pygame.SRCALPHA)
        pygame.draw.rect(ts_bg, (255,255,225,255), (0,0,ts_bg.get_width(),ts_bg.get_height()))
        pygame.draw.rect(ts_bg, (0,0,0,200), (0,0,ts_bg.get_width(),ts_bg.get_height()),1)
        self.screen.blit(ts_bg, (tip_x, 10))
        self.screen.blit(tip_surf, (tip_x+8, 14))

        # ─────────────────────────────────────────────────────────
        #  SETTINGS 오버레이
        # ─────────────────────────────────────────────────────────
        if mode == 'SETTINGS':
            # ── 반투명 오버레이 ──────────────────────────────────
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.rect(ov, (0, 0, 0, 140), (0, 0, W, H))
            self.screen.blit(ov, (0, 0))

            # ── Win95 대화상자 ───────────────────────────────────
            DW, DH = 580, 520
            DX = W // 2 - DW // 2
            DY = H // 2 - DH // 2

            # 창 배경 + raised 테두리
            pygame.draw.rect(self.screen, C_SIDEBAR_B, (DX, DY, DW, DH))
            pygame.draw.lines(self.screen, (255,255,255), False,
                [(DX, DY+DH-1),(DX, DY),(DX+DW-1, DY)], 2)
            pygame.draw.lines(self.screen, (64,64,64), False,
                [(DX, DY+DH-1),(DX+DW-1, DY+DH-1),(DX+DW-1, DY)], 2)

            # 타이틀바
            TB = pygame.Rect(DX+2, DY+2, DW-4, 20)
            pygame.draw.rect(self.screen, (0, 0, 128), TB)
            pygame.draw.rect(self.screen, (0, 0, 100), (DX+DW-22, DY+3, 18, 16))
            pygame.draw.lines(self.screen, (200,200,200), False,
                [(DX+DW-22,DY+3),(DX+DW-22,DY+19),(DX+DW-4,DY+19)], 1)
            x_t = self.title_font.render("×", True, (200,200,200))
            self.screen.blit(x_t, (DX+DW-16, DY+4))
            title_t = self.font.render("  Zenith Motion  —  Shortcuts & Info", True, (255,255,255))
            self.screen.blit(title_t, (TB.x+4, TB.y+3))

            # ── 탭 영역 ──────────────────────────────────────────
            if not hasattr(self, '_settings_tab'): self._settings_tab = 0
            TAB_Y = DY + 26
            tabs = ["Keyboard", "Physics", "About"]
            TAB_W = 90
            for ti, tlbl in enumerate(tabs):
                tx = DX + 6 + ti * (TAB_W + 2)
                is_sel = (self._settings_tab == ti)
                tab_r = pygame.Rect(tx, TAB_Y, TAB_W, 22)
                if is_sel:
                    pygame.draw.rect(self.screen, C_SIDEBAR_B, tab_r)
                    pygame.draw.lines(self.screen, (255,255,255), False,
                        [(tx, TAB_Y+21),(tx, TAB_Y),(tx+TAB_W-1, TAB_Y)], 1)
                    pygame.draw.lines(self.screen, (64,64,64), False,
                        [(tx, TAB_Y+21),(tx+TAB_W-1, TAB_Y+21),(tx+TAB_W-1, TAB_Y)], 1)
                    pygame.draw.line(self.screen, C_SIDEBAR_B, (tx+1, TAB_Y+21), (tx+TAB_W-2, TAB_Y+21), 1)
                else:
                    pygame.draw.rect(self.screen, (180,178,170), tab_r)
                    pygame.draw.lines(self.screen, (255,255,255), False,
                        [(tx, TAB_Y+21),(tx, TAB_Y),(tx+TAB_W-1, TAB_Y)], 1)
                    pygame.draw.lines(self.screen, (64,64,64), False,
                        [(tx, TAB_Y+21),(tx+TAB_W-1, TAB_Y+21),(tx+TAB_W-1, TAB_Y)], 1)
                tc = C_TEXT if is_sel else (80,80,80)
                tt = self.title_font.render(tlbl, True, tc)
                self.screen.blit(tt, tt.get_rect(center=tab_r.center))

            # 탭 아래 구분선 (선택 탭 빈칸 처리)
            pygame.draw.line(self.screen, (64,64,64),
                (DX+2, TAB_Y+21), (DX+DW-2, TAB_Y+21), 1)
            sel_tx = DX + 6 + self._settings_tab * (TAB_W + 2)
            pygame.draw.line(self.screen, C_SIDEBAR_B,
                (sel_tx+1, TAB_Y+21), (sel_tx+TAB_W-1, TAB_Y+21), 1)

            # ── 탭 콘텐츠 영역 ───────────────────────────────────
            CONTENT_Y = TAB_Y + 24
            CONTENT_H = DH - (CONTENT_Y - DY) - 42
            cx_l = DX + 14
            cx_r = DX + DW//2 + 6

            def _section(label, y):
                ls = self.title_font.render(label, True, C_TEXT_DIM)
                lb = pygame.Surface((ls.get_width()+8, ls.get_height()), pygame.SRCALPHA)
                lb.fill((*C_SIDEBAR_B, 255)); lb.blit(ls, (4, 0))
                pygame.draw.line(self.screen, (128,128,128),
                    (DX+8, y+6), (DX+DW-8, y+6), 1)
                self.screen.blit(lb, (DX+14, y))
                return y + 18

            def _krow(action, key, y, col=0):
                xbase = cx_l if col == 0 else cx_r
                ks = self.title_font.render(action, True, C_TEXT)
                self.screen.blit(ks, (xbase, y))
                kw = DW//2 - 28
                kbr = pygame.Rect(xbase + kw - 60, y-1, 62, 15)
                pygame.draw.rect(self.screen, (200,198,190), kbr)
                pygame.draw.lines(self.screen, (64,64,64), False,
                    [(kbr.left,kbr.bottom-1),(kbr.left,kbr.top),(kbr.right-1,kbr.top)], 1)
                pygame.draw.lines(self.screen, (255,255,255), False,
                    [(kbr.left,kbr.bottom-1),(kbr.right-1,kbr.bottom-1),(kbr.right-1,kbr.top)], 1)
                kt = self.title_font.render(key, True, (0,0,0))
                self.screen.blit(kt, kt.get_rect(center=kbr.center))

            if self._settings_tab == 0:
                # ── 키보드 탭 ──
                y = CONTENT_Y + 4
                # 2열 레이아웃
                left_col = [
                    ("TOOLS",  None),
                    ("Select",       "S"),
                    ("Weld",         "W"),
                    ("Hinge",        "H"),
                    ("Velocity",     "V"),
                    ("Delete",       "D"),
                    ("Pin",          "P"),
                    ("OBJECTS", None),
                    ("Circle",       "C"),
                    ("Box",          "B"),
                    ("Triangle",     "R"),
                    ("T-Shape",      "O"),
                    ("H-Shape",      "E"),
                    ("Right Tri",    "J"),
                    ("Image",        "I"),
                ]
                right_col = [
                    ("LINKS",  None),
                    ("Spring",       "K"),
                    ("Attach",       "A"),
                    ("String",       "T"),
                    ("Pulley",       "U"),
                    ("ACTIONS", None),
                    ("Pause/Resume", "Space"),
                    ("Undo",         "Ctrl+Z"),
                    ("Finish Pulley","Enter"),
                    ("Cancel",       "Esc"),
                    ("Rotate (phys)","Hold G"),
                    ("Pin/Unpin",    "T"),
                    ("Export (Bake)","X"),
                    ("Settings",     "F1"),
                    ("Sidebar",      "Tab"),
                ]
                yl, yr = y, y
                for name, key in left_col:
                    if key is None:
                        yl = _section(name, yl)
                    else:
                        _krow(name, key, yl, col=0)
                        yl += 17
                for name, key in right_col:
                    if key is None:
                        yr = _section(name, yr)
                    else:
                        _krow(name, key, yr, col=1)
                        yr += 17

            elif self._settings_tab == 1:
                # ── 물리 설정 탭 ──
                y = CONTENT_Y + 8
                rows = [
                    ("SIMULATION", None),
                    ("Sub-steps",     f"{int(bake_config.get('substeps',10))}×  (higher = more accurate)"),
                    ("Constraint iter", f"auto-scaled with substeps (20~60×)"),
                    ("World Width",   f"{int(bake_config.get('world_w',2000))} px"),
                    ("World Height",  f"{int(bake_config.get('world_h',2000))} px"),
                    ("PHYSICS CONSTANTS", None),
                    ("Gravity",       "900 px/s²  (downward)"),
                    ("Air Drag",      "Per-object  (0 = no drag)"),
                    ("Restitution",   "Per-object  (0 = inelastic, 1 = elastic)"),
                    ("Friction μ",    "Per-object Coulomb  (0 ~ 0.1)"),
                    ("COLLISION", None),
                    ("Method",        "XPBD  (eXtended PBD)"),
                    ("Iterations",    "20~60×  per substep (substep-scaled)"),
                    ("Normal Force",  "Contact impulse integration"),
                    ("Wall bounce",   "Per-object restitution + friction"),
                    ("Circle-Circle", "Impulse pre-pass + position correction"),
                    ("STRESS", None),
                    ("Peak Stress",   "Per-constraint F=m·Δpos/dt²  (max)"),
                    ("Internal",      "Structural constraint stress sum"),
                    ("Tension",       "Global attach / string / pulley"),
                ]
                for label, val in rows:
                    if val is None:
                        y = _section(label, y)
                    else:
                        ls = self.title_font.render(label, True, C_TEXT_DIM)
                        vs = self.title_font.render(val, True, C_TEXT)
                        self.screen.blit(ls, (DX+20, y))
                        self.screen.blit(vs, (DX+160, y))
                        y += 18

            else:
                # ── About 탭 ──
                y = CONTENT_Y + 16
                lines_about = [
                    ("Zenith Motion", True),
                    ("Interactive Physics Simulator", False),
                    ("", False),
                    ("Engine:   PBD (Position-Based Dynamics)", False),
                    ("Renderer: Pygame / Win95 UI style", False),
                    ("Language: Python 3", False),
                    ("", False),
                    ("Controls at a glance:", True),
                    ("  Drag object →  Move", False),
                    ("  Scroll       →  Zoom in/out", False),
                    ("  MMB drag     →  Pan camera", False),
                    ("  Space        →  Pause / Resume", False),
                    ("  Right-click slider → Type exact value", False),
                    ("", False),
                    ("Powered by Claude (Anthropic)", False),
                ]
                for text, bold in lines_about:
                    if not text:
                        y += 6; continue
                    fnt = self.font if bold else self.title_font
                    col = C_ACCENT if bold else C_TEXT
                    self.screen.blit(fnt.render(text, True, col), (DX+24, y))
                    y += 20 if bold else 17

            # ── 하단 닫기 버튼 ───────────────────────────────────
            close_r = pygame.Rect(DX + DW//2 - 40, DY + DH - 34, 80, 24)
            pygame.draw.rect(self.screen, C_SIDEBAR_B, close_r)
            pygame.draw.lines(self.screen, (255,255,255), False,
                [(close_r.left,close_r.bottom-1),(close_r.left,close_r.top),(close_r.right-1,close_r.top)], 1)
            pygame.draw.lines(self.screen, (64,64,64), False,
                [(close_r.left,close_r.bottom-1),(close_r.right-1,close_r.bottom-1),(close_r.right-1,close_r.top)], 1)
            ct = self.title_font.render("Close  [F1]", True, C_TEXT)
            self.screen.blit(ct, ct.get_rect(center=close_r.center))
            self.slider_coords['settings_close'] = (close_r.x, close_r.y, close_r.w, close_r.h)
            self.slider_coords['settings_tabs']  = [(DX+6+i*(TAB_W+2), TAB_Y, TAB_W, 22)
                                                     for i in range(len(tabs))]

        # ── 우클릭 드래그 선택 박스 ──────────────────────────────────────
        if rbox_start and rbox_end:
            rx1 = min(rbox_start[0], rbox_end[0])
            ry1 = min(rbox_start[1], rbox_end[1])
            rw  = abs(rbox_end[0] - rbox_start[0])
            rh  = abs(rbox_end[1] - rbox_start[1])
            if rw > 2 and rh > 2:
                # IP 스타일: 검정 점선 선택 박스
                rbox_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
                pygame.draw.rect(rbox_surf, (0, 0, 128, 20), (0, 0, rw, rh))
                pygame.draw.rect(rbox_surf, (0, 0, 0, 220), (0, 0, rw, rh), 1)
                self.screen.blit(rbox_surf, (rx1, ry1))

        pygame.display.flip()