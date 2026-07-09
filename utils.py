"""
utils.py — 씬 유틸리티 모듈 (main.py에서 분리)

포함:
- 다이얼로그: open_image_dialog, ask_exact_value
- AttachProxy / hit_test_attach : attach 막대 선택용 래퍼
- find_attach_target            : 클릭 위치 → 부착점 탐색/생성 (5단계 우선순위)
- apply_physical_rotation       : weld 그룹 단위 물리 회전
- point_in_polygon / obj_hit_test : 클릭 판정
- UndoManager                   : ★ 압축 스냅샷 기반 실행취소 (메모리 개선)

★ UndoManager 업그레이드 내용:
  기존 _push_undo는 씬 전체를 deepcopy해 객체 그래프 그대로 스택에 쌓았다.
  → 객체가 많으면 스냅샷 50개 × 전체 파티클/제약 객체가 메모리에 상주.
  이제 pickle 직렬화 + zlib 압축으로 바이트 형태로 보관한다.
  - 파티클/제약 객체는 좌표·수치 위주라 압축률이 매우 높음 (보통 5~20배 절감)
  - 내부 참조(attach/hinge/pulley의 p1/p2)는 pickle이 그래프째 보존하므로
    복원 시에도 정확히 같은 파티클을 가리킨다.
  - pygame.Surface는 직렬화 불가 → 이미지 리스트로 따로 보관 후 복원 시 재연결
  - pickle 실패 시 기존 deepcopy 방식으로 자동 폴백 (안전성 유지)
"""
import pygame
import math
import copy
import pickle
import zlib

from objects import (Box, Circle, Triangle, RightTriangle, Constraint, Particle,
                     TrueSpring, ImageBlock, StringObj, PolygonShape,
                     HShape, TShape, CompoundShape)


# ─────────────────────────────────────────────────────────────────────────────
# tkinter 다이얼로그 (★ 지연 임포트 — tkinter 미설치 환경에서도 본체 실행 가능)
# ─────────────────────────────────────────────────────────────────────────────

def _make_tk_root():
    """숨겨진 topmost tk 루트 생성. tkinter 미설치 시 None."""
    try:
        import tkinter as tk
    except ImportError:
        print("[DIALOG] tkinter가 설치돼 있지 않아 입력 창을 열 수 없습니다.")
        return None
    root = tk.Tk()
    root.attributes('-topmost', True)
    root.withdraw()
    return root


def open_image_dialog():
    root = _make_tk_root()
    if root is None: return None
    from tkinter import filedialog
    path = filedialog.askopenfilename(title="이미지 선택", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp")])
    root.destroy()
    return path


def ask_exact_value(title, prompt_text, initial):
    root = _make_tk_root()
    if root is None: return None
    import tkinter.simpledialog as simpledialog
    val = simpledialog.askfloat(title, prompt_text, initialvalue=initial)
    root.destroy()
    return val


def ask_exact_text(title, prompt_text, initial):
    root = _make_tk_root()
    if root is None: return None
    import tkinter.simpledialog as simpledialog
    val = simpledialog.askstring(title, prompt_text, initialvalue=initial)
    root.destroy()
    return val


# ─────────────────────────────────────────────────────────────────────────────
# Attach 막대 선택용 가상 오브젝트
# ─────────────────────────────────────────────────────────────────────────────

class AttachProxy:
    """global constraint(attach 막대) 하나를 info 패널에 표시하기 위한 래퍼."""
    def __init__(self, constraint):
        self.constraint = constraint
        self.particles  = [constraint.p1, constraint.p2]
        self.name       = "Attach"
        self.color      = (200, 180, 0)
        self.friction   = getattr(constraint.p1.parent, 'friction', 0.01) if constraint.p1.parent else 0.01
        self.restitution= 0.5
        self.air_drag   = 0.0
        self.z_layer    = 0
        self.mass       = ((constraint.p1.mass if not constraint.p1.is_static else 0) +
                           (constraint.p2.mass if not constraint.p2.is_static else 0))
        self.speed_history = []
        # info 패널이 필요로 하는 누산값 더미
        self.tension_acc = 0.0; self.spring_acc = 0.0
        self.int_acc     = 0.0; self.normal_acc = 0.0; self.stress_max = 0.0

    def get_angle(self):
        dx = self.constraint.p2.pos.x - self.constraint.p1.pos.x
        dy = self.constraint.p2.pos.y - self.constraint.p1.pos.y
        return math.degrees(math.atan2(dy, dx))

    def set_mass(self, m):
        self.mass = m   # attach는 질량 변경 불가 — 무시

    def set_velocity(self, vx, vy, dt):
        pass  # attach는 속도 설정 불가


def hit_test_attach(engine, world_pos, threshold=10.0):
    """global constraint 중 attach 막대(노란선)를 클릭했는지 검사.
    반환: AttachProxy 또는 None
    """
    pos = pygame.math.Vector2(world_pos)
    for c in engine.global_constraints:
        # weld/hinge 제외, is_solid=True인 막대만
        style = getattr(c, 'style', 'line')
        if style in ('weld', 'hinge'): continue
        p1, p2 = c.p1.pos, c.p2.pos
        ab = p2 - p1
        ab_len_sq = ab.length_squared()
        if ab_len_sq < 1: continue
        t = max(0.0, min(1.0, (pos - p1).dot(ab) / ab_len_sq))
        closest = p1 + ab * t
        if closest.distance_to(pos) <= threshold:
            return AttachProxy(c)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 물리 회전
# ─────────────────────────────────────────────────────────────────────────────

def apply_physical_rotation(obj, target_angle_deg, engine, is_paused):
    current_angle = obj.get_angle() if hasattr(obj, 'get_angle') else 0.0
    # 각도 차이를 -180~+180 범위로 정규화 (가장 짧은 방향으로 회전)
    delta_deg = (target_angle_deg - current_angle + 180) % 360 - 180
    delta_rad = math.radians(delta_deg)
    if abs(delta_rad) < 1e-9: return

    weld_gid = getattr(obj, 'weld_group_id', obj.collision_group)
    welded_objs = [o for o in engine.objects if getattr(o, 'weld_group_id', o.collision_group) == weld_gid]
    all_parts = [p for o in welded_objs for p in o.particles]
    if not all_parts: return

    group_center = sum((p.pos for p in all_parts), pygame.math.Vector2()) / len(all_parts)
    cos_a, sin_a = math.cos(delta_rad), math.sin(delta_rad)

    for p in all_parts:
        r_pos = p.pos - group_center
        p.pos = group_center + pygame.math.Vector2(r_pos.x * cos_a - r_pos.y * sin_a, r_pos.x * sin_a + r_pos.y * cos_a)
        if is_paused:
            p.old_pos = p.pos.copy()
        else:
            r_old = p.old_pos - group_center
            p.old_pos = group_center + pygame.math.Vector2(r_old.x * cos_a - r_old.y * sin_a, r_old.x * sin_a + r_old.y * cos_a)

    for o in welded_objs:
        if isinstance(o, Circle): o.angle += math.degrees(delta_rad)


# ─────────────────────────────────────────────────────────────────────────────
# Attach 대상 탐색
# ─────────────────────────────────────────────────────────────────────────────

def find_attach_target(engine, mouse_world, cam):
    """
    클릭 위치에서 attach 대상 Particle을 찾거나 새로 생성해서 반환.
    반환: Particle (이미 존재하거나 새로 만든 것), 없으면 None

    우선순위:
    1. 기존 파티클 15px 이내  → 그 파티클 재사용
    2. 실/스프링 선분 20px 이내 → 선분 위 보간점에 새 파티클 생성
    3. 원 내부/표면              → 원 중심 파티클 사용
    4. 폴리곤 내부              → 클릭 위치에 새 파티클 생성하고 기존 파티클들과 연결
    5. 외곽선 15px 이내         → 기존 edge 방식 (선분 위 보간점)
    """
    pos = pygame.math.Vector2(mouse_world)
    mx, my = pos.x, pos.y

    # ── 1. 기존 파티클 15px 이내 ─────────────────────────────────────
    nearest_p, nearest_dist = None, 15.0
    for obj in engine.objects:
        for p in obj.particles:
            d = p.pos.distance_to(pos)
            if d < nearest_dist:
                nearest_dist, nearest_p = d, p
    if nearest_p:
        return nearest_p

    # ── 2. 실(StringObj) / 스프링(TrueSpring) 선분 20px 이내 ─────────
    for obj in engine.objects:
        if not isinstance(obj, (StringObj, TrueSpring)):
            continue
        for c in obj.constraints:
            ab = c.p2.pos - c.p1.pos
            ab_sq = ab.length_squared()
            if ab_sq < 1: continue
            t = max(0.0, min(1.0, (pos - c.p1.pos).dot(ab) / ab_sq))
            closest = c.p1.pos + ab * t
            dist = closest.distance_to(pos)
            if dist < 20.0:
                # 선분 위 보간점에 새 파티클 생성, 인접 두 파티클과 연결
                pt = Particle(closest.x, closest.y, radius=3, mass=0.5)
                obj.particles.append(pt)
                pt.parent = obj
                obj.constraints.append(Constraint(pt, c.p1, stiffness=1.0, is_solid=False, parent=obj))
                obj.constraints.append(Constraint(pt, c.p2, stiffness=1.0, is_solid=False, parent=obj))
                return pt

    # ── 3. Circle 내부/표면 ──────────────────────────────────────────
    for obj in engine.objects:
        if isinstance(obj, Circle):
            cp = obj.particles[0]
            if cp.pos.distance_to(pos) <= obj.radius:
                return cp  # 원은 중심 파티클 그대로 사용

    # ── 4. 폴리곤 내부 (Box / Triangle / PolygonShape / ImageBlock) ──
    for obj in engine.objects:
        pts_for_poly = None
        if isinstance(obj, Box):
            pts_for_poly = [(p.pos.x, p.pos.y) for p in obj.particles[:4]]
        elif isinstance(obj, Triangle):
            pts_for_poly = [(p.pos.x, p.pos.y) for p in obj.particles[:3]]
        elif isinstance(obj, RightTriangle):
            pts_for_poly = [(p.pos.x, p.pos.y) for p in obj.particles[:3]]
        elif isinstance(obj, (PolygonShape, HShape, TShape, CompoundShape)):
            pts_for_poly = getattr(obj, 'render_particles', [])
            pts_for_poly = [(p.pos.x, p.pos.y) for p in pts_for_poly]
        elif isinstance(obj, ImageBlock):
            # ★ 고정 둘레 목록 사용 (attach로 파티클이 추가돼도 오염 안 됨)
            perim = getattr(obj, 'render_particles', [])
            if len(perim) >= 3:
                pts_for_poly = [(p.pos.x, p.pos.y) for p in perim]

        if pts_for_poly and point_in_polygon(mx, my, pts_for_poly):
            # 클릭 위치에 새 파티클 생성, 모든 기존 파티클과 현재 거리로 연결
            pt = Particle(mx, my, radius=3, mass=0.5)
            existing = list(obj.particles)
            obj.particles.append(pt)
            pt.parent = obj
            for ep in existing:
                obj.constraints.append(Constraint(pt, ep, stiffness=1.0, is_solid=False, parent=obj))
            return pt

    # ── 5. 외곽선 15px 이내 (기존 edge 방식) ─────────────────────────
    best_pt, best_edge, best_obj, best_dist = None, None, None, 15.0
    for obj in engine.objects:
        if isinstance(obj, Circle): continue  # 이미 3에서 처리
        for c in obj.constraints:
            if not getattr(c, 'is_solid', False): continue
            ab = c.p2.pos - c.p1.pos
            ab_sq = ab.length_squared()
            if ab_sq < 1: continue
            t = max(0.0, min(1.0, (pos - c.p1.pos).dot(ab) / ab_sq))
            closest = c.p1.pos + ab * t
            dist = closest.distance_to(pos)
            if dist < best_dist:
                best_dist, best_pt, best_edge, best_obj = dist, closest, c, obj
    if best_pt:
        pt = Particle(best_pt.x, best_pt.y, radius=3, mass=0.5)
        best_obj.particles.append(pt)
        pt.parent = best_obj
        best_obj.constraints.append(Constraint(pt, best_edge.p1, stiffness=1.0, is_solid=False, parent=best_obj))
        best_obj.constraints.append(Constraint(pt, best_edge.p2, stiffness=1.0, is_solid=False, parent=best_obj))
        return pt

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 클릭 판정
# ─────────────────────────────────────────────────────────────────────────────

def point_in_polygon(px, py, polygon):
    n = len(polygon)
    if n < 3: return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside


def obj_hit_test(obj, world_pos, cam):
    """물체의 채워진 영역 또는 꼭짓점/중심 근처를 클릭했는지 판별"""
    mx, my = world_pos.x, world_pos.y

    if isinstance(obj, Circle):
        p = obj.particles[0]
        return p.pos.distance_to(world_pos) <= obj.radius

    if isinstance(obj, ImageBlock):
        # ★ 확정 판정: 외곽 링 내부 또는 외곽선 8px 이내만 선택.
        #   투명(빈) 영역 클릭은 False — 범용 중심 폴백으로 안 넘어감.
        rp = getattr(obj, 'render_particles', [])
        if len(rp) >= 3:
            pts = [(p.pos.x, p.pos.y) for p in rp]
            if point_in_polygon(mx, my, pts):
                return True
            n = len(rp)
            for i in range(n):
                a, b = rp[i].pos, rp[(i + 1) % n].pos
                ab = b - a
                L2 = ab.length_squared()
                if L2 < 1: continue
                t = max(0.0, min(1.0, (world_pos - a).dot(ab) / L2))
                if (a + ab * t).distance_to(world_pos) < 8:
                    return True
            return False
        # render_particles가 없는 비정상 상태만 아래 범용 판정으로

    if isinstance(obj, Box):
        pts = [(p.pos.x, p.pos.y) for p in obj.particles[:4]]
        if point_in_polygon(mx, my, pts): return True

    elif isinstance(obj, Triangle):
        pts = [(p.pos.x, p.pos.y) for p in obj.particles[:3]]
        if point_in_polygon(mx, my, pts): return True

    elif isinstance(obj, RightTriangle):
        pts = [(p.pos.x, p.pos.y) for p in obj.particles[:3]]
        if point_in_polygon(mx, my, pts): return True
    elif isinstance(obj, (PolygonShape, HShape, TShape, CompoundShape, ImageBlock)):
        # ★ ImageBlock도 고정 둘레 목록(render_particles)으로 판정 — 선택 안정화
        rp = getattr(obj, 'render_particles', [])
        if rp:
            pts = [(p.pos.x, p.pos.y) for p in rp]
            if point_in_polygon(mx, my, pts): return True

    elif isinstance(obj, (StringObj, TrueSpring)):
        for c in obj.constraints:
            ab = c.p2.pos - c.p1.pos
            ab_len_sq = ab.length_squared()
            if ab_len_sq < 1: continue
            ap = world_pos - c.p1.pos
            t = max(0.0, min(1.0, ap.dot(ab) / ab_len_sq))
            closest = c.p1.pos + ab * t
            if closest.distance_to(world_pos) < 8:
                return True
        return False

    if hasattr(obj, 'ref_p1') and hasattr(obj, 'ref_p2'):
        perim = [p for p in obj.particles if p != obj.particles[0]]
        if len(perim) >= 3:
            pts = [(p.pos.x, p.pos.y) for p in perim]
            if point_in_polygon(mx, my, pts): return True

    center = sum((p.pos for p in obj.particles), pygame.math.Vector2()) / len(obj.particles)
    if center.distance_to(world_pos) < 36: return True
    for p in obj.particles:
        if p.pos.distance_to(world_pos) < max(8, getattr(p, 'radius', 5) + 4): return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# ★ UndoManager — 압축 스냅샷 기반 실행취소
# ─────────────────────────────────────────────────────────────────────────────

class UndoManager:
    """씬 스냅샷을 pickle+zlib로 압축 보관하는 실행취소 스택.

    기존 deepcopy 방식 대비 메모리 사용량이 크게 줄어든다
    (좌표 수치 위주 데이터라 압축률이 높음). pickle은 객체 그래프 전체를
    직렬화하므로 attach/hinge/pulley 제약의 p1/p2 내부 참조도
    복원 후 정확히 같은 파티클 객체를 가리킨다.

    스택 항목 형식:
      ('z', compressed_bytes, images, label)   ← 압축 스냅샷 (기본)
      ('d', bundle_dict,      images, label)   ← deepcopy 폴백
    """

    def __init__(self, max_size=50, verbose=True):
        self.max_size = max_size
        self.verbose = verbose
        self._stack = []

    def __len__(self):
        return len(self._stack)

    def __bool__(self):
        return bool(self._stack)

    # ── 저장 ────────────────────────────────────────────────────────
    def push(self, engine, label="action"):
        """현재 씬 전체를 스냅샷으로 저장 — 내부 참조(attach/hinge/pulley) 유지"""
        try:
            # pygame.Surface는 pickle/deepcopy 불가 → 임시 제거 후 복원
            images = [getattr(obj, 'image', None) for obj in engine.objects]
            for obj in engine.objects:
                obj.image = None

            bundle = {
                'objects':            engine.objects,
                'global_constraints': engine.global_constraints,
                'pulley_constraints': engine.pulley_constraints,
            }

            entry = None
            try:
                # ★ 핵심: 한 번의 pickle로 객체 그래프째 직렬화 + zlib 압축
                raw = pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL)
                packed = zlib.compress(raw, level=6)
                entry = ('z', packed, images, label)
                if self.verbose:
                    print(f"[UNDO] 저장 ({label}) — {len(raw)//1024}KB → "
                          f"{len(packed)//1024}KB 압축, 스택: {len(self._stack)+1}")
            except Exception as pe:
                # pickle 불가 객체가 섞인 경우 → deepcopy 폴백
                bundle_copy = copy.deepcopy(bundle)
                entry = ('d', bundle_copy, images, label)
                if self.verbose:
                    print(f"[UNDO] 저장 ({label}) — deepcopy 폴백 ({pe}), "
                          f"스택: {len(self._stack)+1}")
            finally:
                # 원본 image 복원
                for obj, img in zip(engine.objects, images):
                    obj.image = img

            self._stack.append(entry)
            if len(self._stack) > self.max_size:
                self._stack.pop(0)
        except Exception as e:
            print(f"[UNDO] 저장 실패: {e}")

    # ── 복원 ────────────────────────────────────────────────────────
    def pop(self):
        """가장 최근 스냅샷을 꺼내 dict로 반환. 비어 있으면 None.
        반환 dict: {'objects', 'global_constraints', 'pulley_constraints',
                    'images', 'label'}
        이미지(Surface)는 objects에 인덱스 순서대로 이미 재연결돼 있다.
        """
        if not self._stack:
            return None
        kind, payload, images, label = self._stack.pop()
        try:
            if kind == 'z':
                bundle = pickle.loads(zlib.decompress(payload))
            else:
                bundle = payload

            # image(Surface) 재연결 — 인덱스 대응 (Surface는 불변이므로 공유 OK)
            for obj, img in zip(bundle['objects'], images):
                obj.image = img

            bundle['images'] = images
            bundle['label'] = label
            return bundle
        except Exception as e:
            print(f"[UNDO] 복원 실패: {e}")
            return None