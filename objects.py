import pygame
import math
import os

class Particle:
    def __init__(self, x, y, radius=10, mass=1.0, is_static=False):
        self.pos = pygame.math.Vector2(x, y)
        self.old_pos = pygame.math.Vector2(x, y)
        self.radius = radius
        self.mass = mass
        self.is_static = is_static
        self.parent = None
        self.normal_offset = pygame.math.Vector2(0, 0)

class Constraint:
    def __init__(self, p1, p2, length=None, stiffness=1.0, is_solid=False, style="line", parent=None):
        self.p1 = p1
        self.p2 = p2
        self.length = length if length else p1.pos.distance_to(p2.pos)
        self.stiffness = stiffness
        self.is_solid = is_solid
        self.style = style
        self.parent = parent
        self.edge_normal = None   # (nx, ny) 고정 외부 노말 (오목 폴리곤용)
        self.no_collision = False  # True이면 이 attach 막대 양쪽 물체 간 충돌 무시

class PulleyConstraint:
    def __init__(self, pts, stiffness=1.0):
        self.pts = pts 
        self.length = sum(pts[i].pos.distance_to(pts[i+1].pos) for i in range(len(pts)-1))
        self.stiffness = stiffness
        self.parent = "global"

class PhysicsObject:
    def __init__(self):
        self.particles = []
        self.constraints = []
        self.color = (150, 150, 150)
        self.name = "Object"
        self.image = None
        self.angle = 0
        self.collision_group = id(self)
        self.friction     = 0.01   # 표면 쿨롱 마찰계수 (0~1)
        self.restitution  = 0.5    # 반발계수 e (0=완전비탄성, 1=완전탄성)
        self.air_drag     = 0.0    # 물체별 공기저항 추가 계수 (0~1)
        self.z_layer      = 0      # Z-인덱스: 같은 값끼리만 충돌
        self.mass = 5.0
        self.speed_history = []

    def assign_parents(self):
        for p in self.particles: p.parent = self
        for c in self.constraints: c.parent = self
        self._base_particle_count = len(self.particles)   # 생성 시 고유 파티클 수 고정
        self.set_mass(self.mass)

    def set_mass(self, m):
        self.mass = m
        if self.particles:
            # 생성 이후 attach/hinge로 추가된 파티클은 제외하고 균등 분배
            base_n = getattr(self, '_base_particle_count', len(self.particles))
            base_n = max(1, min(base_n, len(self.particles)))
            pmass = m / base_n
            for p in self.particles[:base_n]:
                p.mass = pmass
            # 추가된 파티클은 매우 작은 질량 (구조적 역할만)
            for p in self.particles[base_n:]:
                p.mass = max(0.01, pmass * 0.05)

    def set_velocity(self, vx, vy, dt):
        if dt <= 0: dt = 0.016
        for p in self.particles:
            if not p.is_static:
                p.old_pos = p.pos - pygame.math.Vector2(vx, vy) * dt
        # ★ pause 중 설정한 초기 속도 기억 — 재생(play) 시점에 적용된다.
        #   (pause 중에는 paused_solve가 old_pos를 매 프레임 덮어쓰므로
        #    Verlet 인코딩만으로는 속도가 보존되지 않는다.)
        self.pending_velocity = pygame.math.Vector2(vx, vy)

    def load_image(self, image_path, size):
        if os.path.exists(image_path):
            img = pygame.image.load(image_path).convert_alpha()
            self.image = pygame.transform.smoothscale(img, size)
            return True
        return False

    def get_angle(self):
        if len(self.particles) < 2: return getattr(self, 'angle', 0.0)
        center = sum((p.pos for p in self.particles), pygame.math.Vector2()) / len(self.particles)
        dx = self.particles[0].pos.x - center.x
        dy = self.particles[0].pos.y - center.y
        return math.degrees(math.atan2(dy, dx))

class PolygonShape(PhysicsObject):
    def __init__(self, x, y, width, height, shape_type):
        super().__init__()
        self.name = shape_type
        w, h = width / 2, height / 2
        
        if shape_type == "TSHAPE":
            pts = [(-w, h), (w, h), (w, h/3), (w/3, h/3), (w/3, -h), (-w/3, -h), (-w/3, h/3), (-w, h/3)]
            self.color = (140, 140, 140)
            # ★ 오목 폴리곤 SAT용 볼록 분해 인덱스 (collision.get_convex_hulls)
            #   하단 가로막대: 0,1,2,7 / 상단 세로막대: 3,4,5,6
            self.hull_indices = [[0, 1, 2, 7], [3, 4, 5, 6]]


            
        self.render_particles = []
        for px, py in pts:
            p = Particle(x + px, y + py, radius=5)
            self.particles.append(p)
            self.render_particles.append(p)
            
        center_p = Particle(x, y, radius=5)
        self.particles.append(center_p)
        n = len(self.render_particles)

        # 폴리곤 중심 계산 (외부 노말 방향 결정에 사용)
        cx_local = sum(px for px, py in pts) / n
        cy_local = sum(py for px, py in pts) / n

        for i in range(n):
            rp1 = self.render_particles[i]
            rp2 = self.render_particles[(i+1)%n]
            c = Constraint(rp1, rp2, is_solid=True)

            # 엣지 외부 노말 계산 (중심 기준으로 바깥 방향 결정)
            abx = rp2.pos.x - rp1.pos.x
            aby = rp2.pos.y - rp1.pos.y
            nx, ny = aby, -abx  # 후보 노말
            nl = math.hypot(nx, ny)
            if nl > 1e-9:
                nx, ny = nx/nl, ny/nl
                # 엣지 중점 → 폴리곤 중심 방향과 내적: 양수면 중심쪽 → 반전
                midx = (rp1.pos.x + rp2.pos.x) / 2 - x
                midy = (rp1.pos.y + rp2.pos.y) / 2 - y
                to_cx = cx_local - midx
                to_cy = cy_local - midy
                if nx*to_cx + ny*to_cy > 0:
                    nx, ny = -nx, -ny
                c.edge_normal = (nx, ny)
            self.constraints.append(c)

        for i in range(len(self.particles)):
            for j in range(i + 2, len(self.particles)):
                if i == 0 and j == n - 1 and len(self.particles) > n: continue
                self.constraints.append(Constraint(self.particles[i], self.particles[j], is_solid=False))
        self.assign_parents()

    def get_size(self):
        xs = [p.pos.x for p in self.render_particles]
        ys = [p.pos.y for p in self.render_particles]
        return max(xs)-min(xs), max(ys)-min(ys)

    def resize(self, new_w, new_h):
        cx = sum(p.pos.x for p in self.particles) / len(self.particles)
        cy = sum(p.pos.y for p in self.particles) / len(self.particles)
        old_w, old_h = self.get_size()
        if old_w < 1 or old_h < 1: return
        sx = max(5, new_w) / old_w
        sy = max(5, new_h) / old_h
        for p in self.particles:
            lx = p.pos.x - cx
            ly = p.pos.y - cy
            p.pos   = pygame.math.Vector2(cx + lx*sx, cy + ly*sy)
            p.old_pos = p.pos.copy()
        for c in self.constraints:
            c.length = c.p1.pos.distance_to(c.p2.pos)


class Circle(PhysicsObject):
    def __init__(self, x, y, radius):
        super().__init__()
        self.particles.append(Particle(x, y, radius))
        self.color = (170, 170, 170)
        self.name = "Circle"
        self.radius = radius
        self.assign_parents()

    def update_angle(self):
        p = self.particles[0]
        dx = p.pos.x - p.old_pos.x
        self.angle -= (dx / self.radius) * (180 / math.pi)
        
    def get_angle(self):
        return self.angle

    def get_size(self):
        return self.radius * 2, self.radius * 2

    def resize(self, new_w, new_h):
        new_r = max(5, min(new_w, new_h) / 2)
        self.radius = new_r
        self.particles[0].radius = int(new_r)


class Box(PhysicsObject):
    def __init__(self, x, y, width, height):
        super().__init__()
        hw, hh = width / 2, height / 2
        p1 = Particle(x - hw, y - hh, radius=5)
        p2 = Particle(x + hw, y - hh, radius=5)
        p3 = Particle(x + hw, y + hh, radius=5)
        p4 = Particle(x - hw, y + hh, radius=5)
        center_p = Particle(x, y, radius=5)
        self.particles.extend([p1, p2, p3, p4, center_p])
        self.constraints.extend([
            Constraint(p1, p2, is_solid=True), Constraint(p2, p3, is_solid=True),
            Constraint(p3, p4, is_solid=True), Constraint(p4, p1, is_solid=True),
            Constraint(p1, p3, is_solid=False), Constraint(p2, p4, is_solid=False),
            Constraint(center_p, p1, is_solid=False), Constraint(center_p, p2, is_solid=False),
            Constraint(center_p, p3, is_solid=False), Constraint(center_p, p4, is_solid=False)
        ])
        self.color = (150, 150, 150)
        self.name = "Box"
        self.assign_parents()

    def get_angle(self):
        dx = self.particles[1].pos.x - self.particles[0].pos.x
        dy = self.particles[1].pos.y - self.particles[0].pos.y
        return math.degrees(math.atan2(dy, dx))

    def get_size(self):
        p0, p2 = self.particles[0], self.particles[2]
        dx = self.particles[1].pos.x - self.particles[0].pos.x
        dy = self.particles[1].pos.y - self.particles[0].pos.y
        w = math.hypot(dx, dy)
        dx2 = self.particles[2].pos.x - self.particles[1].pos.x
        dy2 = self.particles[2].pos.y - self.particles[1].pos.y
        h = math.hypot(dx2, dy2)
        return w, h

    def resize(self, new_w, new_h):
        cx = sum(p.pos.x for p in self.particles) / len(self.particles)
        cy = sum(p.pos.y for p in self.particles) / len(self.particles)
        hw, hh = max(5, new_w) / 2, max(5, new_h) / 2
        angle_rad = math.radians(self.get_angle())
        ca, sa = math.cos(angle_rad), math.sin(angle_rad)
        for i, (lx, ly) in enumerate([(-hw,-hh),(hw,-hh),(hw,hh),(-hw,hh)]):
            self.particles[i].pos   = pygame.math.Vector2(cx+lx*ca-ly*sa, cy+lx*sa+ly*ca)
            self.particles[i].old_pos = self.particles[i].pos.copy()
        self.particles[4].pos = pygame.math.Vector2(cx, cy)
        self.particles[4].old_pos = self.particles[4].pos.copy()
        for c in self.constraints:
            c.length = c.p1.pos.distance_to(c.p2.pos)


class Triangle(PhysicsObject):
    def __init__(self, x, y, width, height):
        super().__init__()
        hw, hh = width / 2, height / 2
        p1 = Particle(x, y - hh, radius=5)
        p2 = Particle(x - hw, y + hh, radius=5)
        p3 = Particle(x + hw, y + hh, radius=5)
        center_p = Particle(x, y + hh/3, radius=5)
        self.particles.extend([p1, p2, p3, center_p])
        self.constraints.extend([
            Constraint(p1, p2, is_solid=True), Constraint(p2, p3, is_solid=True), Constraint(p3, p1, is_solid=True),
            Constraint(center_p, p1, is_solid=False), Constraint(center_p, p2, is_solid=False), Constraint(center_p, p3, is_solid=False)
        ])
        self.color = (160, 160, 160)
        self.name = "Triangle"
        self.assign_parents()

    def get_angle(self):
        dx = self.particles[2].pos.x - self.particles[1].pos.x
        dy = self.particles[2].pos.y - self.particles[1].pos.y
        return math.degrees(math.atan2(dy, dx))

    def get_size(self):
        p0, p1, p2 = self.particles[0], self.particles[1], self.particles[2]
        w = p1.pos.distance_to(p2.pos)
        h = p0.pos.distance_to((p1.pos + p2.pos) / 2)
        return w, h

    def resize(self, new_w, new_h):
        cx = sum(p.pos.x for p in self.particles) / len(self.particles)
        cy = sum(p.pos.y for p in self.particles) / len(self.particles)
        hw, hh = max(5, new_w) / 2, max(5, new_h) / 2
        angle_rad = math.radians(self.get_angle())
        ca, sa = math.cos(angle_rad), math.sin(angle_rad)
        locals_list = [(0,-hh),(-hw,hh),(hw,hh),(0,hh/3)]
        for i, (lx, ly) in enumerate(locals_list):
            self.particles[i].pos   = pygame.math.Vector2(cx+lx*ca-ly*sa, cy+lx*sa+ly*ca)
            self.particles[i].old_pos = self.particles[i].pos.copy()
        for c in self.constraints:
            c.length = c.p1.pos.distance_to(c.p2.pos)


class StringObj(PhysicsObject):
    def __init__(self, x1, y1, x2, y2, segments=10):
        super().__init__()
        p1 = pygame.math.Vector2(x1, y1)
        p2 = pygame.math.Vector2(x2, y2)
        delta = p2 - p1
        seg_vector = delta / segments
        for i in range(segments + 1):
            pos = p1 + seg_vector * i
            p = Particle(pos.x, pos.y, radius=3, is_static=False) 
            self.particles.append(p)
            if i > 0: self.constraints.append(Constraint(self.particles[i-1], p, stiffness=0.95, is_solid=True))
        self.color = (180, 180, 180)
        self.name = "String"
        self.assign_parents()

class TrueSpring(PhysicsObject):
    def __init__(self, x1, y1, x2, y2):
        super().__init__()
        p1 = Particle(x1, y1, radius=6)
        p2 = Particle(x2, y2, radius=6)
        self.particles.extend([p1, p2])
        self.constraints.append(Constraint(p1, p2, stiffness=0.001, is_solid=False, style="spring"))
        self.color = (130, 130, 130)
        self.name = "Spring"
        self.assign_parents()



class CompoundShape(PhysicsObject):
    """여러 볼록 Box를 강결합해서 만드는 복합 도형.
    오목 폴리곤의 충돌 문제 없이 완벽한 물리 충돌.
    서브클래스에서 _build(x,y,w,h) 를 구현.
    """
    def __init__(self, x, y, width, height):
        super().__init__()
        hw, hh = width/2, height/2
        self._build(x, y, hw, hh)
        self._finalize(x, y)

    def _build(self, x, y, hw, hh):
        raise NotImplementedError

    def _add_box(self, x, y, cx, cy, bw, bh, solid_edges=True):
        """로컬 (cx,cy) 위치에 bw×bh 박스 파티클을 추가하고 제약 연결.
        solid_edges: True(전체), False(전체), 또는 [상,우,하,좌] bool 리스트
        """
        hw2, hh2 = bw/2, bh/2
        corners = [
            Particle(x+cx-hw2, y+cy-hh2, radius=5),
            Particle(x+cx+hw2, y+cy-hh2, radius=5),
            Particle(x+cx+hw2, y+cy+hh2, radius=5),
            Particle(x+cx-hw2, y+cy+hh2, radius=5),
        ]
        for p in corners:
            self.particles.append(p)
        p0,p1,p2,p3 = corners
        # solid_edges가 리스트면 [상,우,하,좌] 순서
        if isinstance(solid_edges, (list, tuple)):
            s_top, s_right, s_bot, s_left = solid_edges
        else:
            s_top = s_right = s_bot = s_left = solid_edges
        self.constraints += [
            Constraint(p0,p1,is_solid=s_top),    # 상
            Constraint(p1,p2,is_solid=s_right),   # 우
            Constraint(p2,p3,is_solid=s_bot),     # 하
            Constraint(p3,p0,is_solid=s_left),    # 좌
            Constraint(p0,p2,is_solid=False),
            Constraint(p1,p3,is_solid=False),
        ]
        return corners

    def _finalize(self, x, y):
        """중심 파티클 추가 + 전체 완전 연결 (rigid body)."""
        center_p = Particle(x, y, radius=5)
        self.particles.append(center_p)

        # id→index 매핑으로 O(n) index() 반복 제거
        all_p = self.particles
        n = len(all_p)
        id_to_idx = {id(p): i for i, p in enumerate(all_p)}
        existing = set()
        for c in self.constraints:
            i1 = id_to_idx.get(id(c.p1), -1)
            i2 = id_to_idx.get(id(c.p2), -1)
            if i1 >= 0 and i2 >= 0:
                existing.add((min(i1, i2), max(i1, i2)))
        for i in range(n):
            for j in range(i+1, n):
                if (i,j) not in existing:
                    self.constraints.append(
                        Constraint(all_p[i], all_p[j], is_solid=False))
        self.assign_parents()

    def get_angle(self):
        if len(self.particles) < 2: return 0.0
        dx = self.particles[1].pos.x - self.particles[0].pos.x
        dy = self.particles[1].pos.y - self.particles[0].pos.y
        return math.degrees(math.atan2(dy, dx))

    def get_size(self):
        xs = [p.pos.x for p in self.particles]
        ys = [p.pos.y for p in self.particles]
        return max(xs)-min(xs), max(ys)-min(ys)

    def resize(self, new_w, new_h):
        cx = sum(p.pos.x for p in self.particles) / len(self.particles)
        cy = sum(p.pos.y for p in self.particles) / len(self.particles)
        new_w, new_h = max(20, new_w), max(20, new_h)
        # 파티클·제약 초기화 후 재빌드
        self.particles.clear()
        self.constraints.clear()
        self.render_particles = []
        if hasattr(self, 'box_groups'):
            self.box_groups = []
        self._build(cx, cy, new_w/2, new_h/2)
        self._finalize(cx, cy)



class HShape(CompoundShape):
    """H 모양: 좌세로 + 우세로 + 가운데 가로"""
    def __init__(self, x, y, width, height):
        self.name = "HShape"
        self.color = (160, 160, 165)
        self.render_particles = []
        super().__init__(x, y, width, height)

    def _build(self, x, y, hw, hh):
        t     = hw * 2/3          # 세로막대 두께
        mid_h = hh * 2/3          # 가운데 가로막대 높이
        # 좌/우 세로막대: 전체 높이, 내측(우/좌) 엣지는 solid=True (외부 충돌용)
        L = self._add_box(x, y, -hw+t/2, 0, t, hh*2)  # [상,우,하,좌] 모두 solid
        R = self._add_box(x, y,  hw-t/2, 0, t, hh*2)
        # 가운데 가로막대: 좌/우 엣지는 세로막대 내벽과 겹침 → solid=False
        M = self._add_box(x, y,  0, 0, hw*2-t*2, mid_h, [True, False, True, False])
        self.box_groups = [L, R, M]
        self.render_particles = [
            L[0], L[1], M[0],
            M[1], R[0], R[1],
            R[2], R[3], M[2],
            M[3], L[2], L[3],
        ]


class TShape(CompoundShape):
    """T 모양: 위 가로 + 아래 세로"""
    def __init__(self, x, y, width, height):
        self.name = "TShape"
        self.color = (140, 140, 145)
        self.render_particles = []
        super().__init__(x, y, width, height)

    def _build(self, x, y, hw, hh):
        arm_h  = hh * 2/3          # 가로막대 높이
        stem_w = hw * 2/3          # 세로막대 너비
        # 위 가로막대: 하단 엣지는 세로막대 상단과 겹침 → 세로막대 범위만 solid=False
        # 단순히 T 하단 전체를 solid=True로 두고 S 상단을 False로 처리
        T = self._add_box(x, y, 0, -hh+arm_h/2, hw*2, arm_h)
        # 세로막대: 상단 엣지가 가로막대 하단과 겹침 → solid=False
        S = self._add_box(x, y, 0,  arm_h/2, stem_w, hh*2-arm_h, [False, True, True, True])
        self.box_groups = [T, S]
        self.render_particles = [
            T[0], T[1], T[2], T[3],
            S[2], S[3],
        ]


class RightTriangle(PhysicsObject):
    """직각 삼각형 — 좌하단에 직각, 우하단+상단으로 구성."""
    def __init__(self, x, y, width, height):
        super().__init__()
        hw, hh = width / 2, height / 2
        # 꼭짓점: p0=좌상, p1=좌하(직각), p2=우하
        # p1에서 두 변(위, 오른쪽)이 수직 → 완벽한 직각
        p0 = Particle(x - hw, y - hh, radius=5)   # 좌상
        p1 = Particle(x - hw, y + hh, radius=5)   # 좌하 (직각)
        p2 = Particle(x + hw, y + hh, radius=5)   # 우하
        # 무게중심 파티클 (내부 강성)
        cx_ = (p0.pos.x + p1.pos.x + p2.pos.x) / 3
        cy_ = (p0.pos.y + p1.pos.y + p2.pos.y) / 3
        cp  = Particle(cx_, cy_, radius=5)
        self.particles.extend([p0, p1, p2, cp])
        self.constraints.extend([
            Constraint(p0, p1, is_solid=True),   # 좌측 수직
            Constraint(p1, p2, is_solid=True),   # 하단 수평 (직각의 두 변)
            Constraint(p2, p0, is_solid=True),   # 빗변
            Constraint(cp, p0, is_solid=False),
            Constraint(cp, p1, is_solid=False),
            Constraint(cp, p2, is_solid=False),
        ])
        self.color = (160, 160, 160)
        self.name = "RightTriangle"
        self.assign_parents()

    def get_angle(self):
        # 하단 엣지(p1→p2) 기준 각도
        dx = self.particles[2].pos.x - self.particles[1].pos.x
        dy = self.particles[2].pos.y - self.particles[1].pos.y
        return math.degrees(math.atan2(dy, dx))

    def get_size(self):
        p0, p1, p2 = self.particles[0], self.particles[1], self.particles[2]
        w = p1.pos.distance_to(p2.pos)   # 하단 (직각의 밑변)
        h = p0.pos.distance_to(p1.pos)   # 좌측 (직각의 높이)
        return w, h

    def resize(self, new_w, new_h):
        cx_ = sum(p.pos.x for p in self.particles) / len(self.particles)
        cy_ = sum(p.pos.y for p in self.particles) / len(self.particles)
        hw, hh = max(5, new_w) / 2, max(5, new_h) / 2
        angle_rad = math.radians(self.get_angle())
        ca, sa = math.cos(angle_rad), math.sin(angle_rad)
        # 로컬 좌표: p0=좌상(-hw,-hh), p1=좌하(-hw,+hh), p2=우하(+hw,+hh)
        # 중심을 삼각형 무게중심 기준으로 설정
        gcx = (-hw - hw + hw) / 3   # = -hw/3
        gcy = (-hh + hh + hh) / 3   # = hh/3
        locals_list = [
            (-hw - gcx, -hh - gcy),   # p0 좌상
            (-hw - gcx,  hh - gcy),   # p1 좌하
            ( hw - gcx,  hh - gcy),   # p2 우하
            (0  - gcx,   0  - gcy),   # cp 중심
        ]
        for i, (lx, ly) in enumerate(locals_list):
            self.particles[i].pos = pygame.math.Vector2(
                cx_ + lx*ca - ly*sa, cy_ + lx*sa + ly*ca)
            self.particles[i].old_pos = self.particles[i].pos.copy()
        for c in self.constraints:
            c.length = c.p1.pos.distance_to(c.p2.pos)


def _convex_hull(points):
    """Andrew's monotone chain 볼록 껍질. points: [(x,y), ...] → hull ring."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return list(pts)
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _signed_area(pts):
    """폴리곤 부호 면적 (shoelace). >0 = 대수적 CCW."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a * 0.5


def _build_foreground_mask(surface):
    """전경 마스크 생성.

    1순위: 알파 채널 (투명 배경 PNG) — 투명한 부분이 충분히 있으면 사용.
    2순위: 색상 분리 — 알파가 거의 전부 불투명이면(스크린샷 등) 네 모서리
      색을 배경으로 추정해, 그와 다른 색의 픽셀만 전경으로 마스킹한다.
    """
    w, h = surface.get_size()
    total = w * h
    alpha_mask = pygame.mask.from_surface(surface)
    filled = alpha_mask.count()

    # 알파로 충분히 모양이 잡히면(전경이 전체의 3~97%) 알파 사용
    if 0.03 * total < filled < 0.97 * total:
        return alpha_mask

    # ── 색상 분리 폴백 ────────────────────────────────────────────────
    # 네 모서리 색을 배경 후보로 수집
    corners = [surface.get_at((0, 0)), surface.get_at((w-1, 0)),
               surface.get_at((0, h-1)), surface.get_at((w-1, h-1))]

    # 각 모서리색 ±tol 범위를 배경으로 마스킹(C 레벨, 빠름) → 모두 합집합(union).
    # 전경 = 배경의 여집합.
    TOL = (60, 60, 60, 255)
    bg_union = pygame.mask.Mask((w, h))
    seen = set()
    for c in corners:
        key = (c.r // 16, c.g // 16, c.b // 16)
        if key in seen:
            continue
        seen.add(key)
        try:
            bg_mask = pygame.mask.from_threshold(surface, (c.r, c.g, c.b), TOL)
        except Exception:
            continue
        bg_union.draw(bg_mask, (0, 0))   # union (OR)

    bg_union.invert()            # 전경 = 배경의 여집합
    mask = bg_union

    # 색 분리가 너무 적게/많이 잡으면 알파로 복귀
    cf = mask.count()
    if cf < 0.01 * total or cf > 0.99 * total:
        return alpha_mask
    return mask


def _douglas_peucker(pts, epsilon):
    """Douglas–Peucker 곡선 단순화 (열린 폴리라인, 반복 구현).
    원본에서 벗어나는 수직거리가 epsilon 이하인 점만 제거 → 곡선 굴곡 보존.
    재귀 대신 스택을 써서 큰 외곽선에서도 RecursionError가 없다."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[n-1] = True
    stack = [(0, n-1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        a, b = pts[i0], pts[i1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        seg_len = math.hypot(dx, dy)
        dmax, idx = 0.0, i0
        for i in range(i0+1, i1):
            px, py = pts[i]
            if seg_len < 1e-9:
                d = math.hypot(px-a[0], py-a[1])
            else:
                d = abs(dy*(px-a[0]) - dx*(py-a[1])) / seg_len
            if d > dmax:
                dmax, idx = d, i
        if dmax > epsilon:
            keep[idx] = True
            stack.append((i0, idx))
            stack.append((idx, i1))
    return [pts[i] for i in range(n) if keep[i]]


def _simplify_ring(pts, max_points=32, epsilon=2.0):
    """닫힌 링을 Douglas–Peucker로 단순화 (모양 보존형).

    ★ 재작성: Visvalingam 방식은 픽셀 단위 외곽선(인접 3점이 거의 일직선,
      삼각형 면적 ≈0)에서 곡선을 통째로 깎아 바운딩 사각형이 돼버렸다.
      Douglas–Peucker는 '원본 곡선에서 벗어나는 거리(epsilon)'를 기준으로
      하므로 갈고리·초승달의 굴곡을 보존하면서 직선 구간만 단순화한다.
    """
    # 연속 중복 제거
    out = []
    for p in pts:
        if not out or out[-1] != p:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    if len(out) <= 4:
        return out

    # 닫힌 링 → 가장 먼 두 점을 끝점으로 잡아 두 폴리라인으로 분할 후 DP
    # (단순히 첫 점을 기준으로 열어도 충분히 동작)
    n = len(out)
    # 무게중심에서 가장 먼 점을 시작점으로 (안정적 분할)
    cx = sum(p[0] for p in out)/n
    cy = sum(p[1] for p in out)/n
    start = max(range(n), key=lambda i: (out[i][0]-cx)**2 + (out[i][1]-cy)**2)
    rolled = out[start:] + out[:start]
    rolled.append(rolled[0])   # 닫기

    eps = epsilon
    simp = _douglas_peucker(rolled, eps)
    if simp and simp[0] == simp[-1]:
        simp = simp[:-1]

    # epsilon을 키워가며 max_points 이하로 (곡선 우선 보존)
    guard = 0
    while len(simp) > max_points and guard < 12:
        eps *= 1.4
        simp = _douglas_peucker(rolled, eps)
        if simp and simp[0] == simp[-1]:
            simp = simp[:-1]
        guard += 1

    return simp if len(simp) >= 3 else out[:max_points]


def _is_convex_ring(pts, eps=1e-7):
    """대수적 CCW 링의 볼록성 검사 (모든 외적 ≥ 0)."""
    n = len(pts)
    if n < 4:
        return True
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        cx, cy = pts[(i + 2) % n]
        if (bx-ax)*(cy-by) - (by-ay)*(cx-bx) < -eps:
            return False
    return True


def _ear_clip(pts):
    """단순 폴리곤(대수적 CCW)을 귀 자르기로 삼각분할.
    반환: [(i, j, k), ...] 인덱스 삼각형 리스트, 실패 시 None."""
    n = len(pts)
    if n < 3:
        return None
    if n == 3:
        return [(0, 1, 2)]
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    def in_tri(p, a, b, c):
        d1 = cross(a, b, p); d2 = cross(b, c, p); d3 = cross(c, a, p)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)
    idx = list(range(n))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < n * n + 100:
        guard += 1
        m = len(idx)
        found = False
        for k in range(m):
            i0, i1, i2 = idx[(k-1) % m], idx[k], idx[(k+1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= 1e-9:
                continue  # 오목(reflex) 또는 일직선 꼭짓점
            ear_ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                if in_tri(pts[j], a, b, c):
                    ear_ok = False
                    break
            if ear_ok:
                tris.append((i0, i1, i2))
                idx.pop(k)
                found = True
                break
        if not found:
            return None  # 자기교차 등으로 귀를 못 찾음 → 폴백
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


class ImageBlock(PhysicsObject):
    """이미지(PNG 등) 물체.

    ★ v2: 오목(concave) 외곽선 정확 충돌.
      마스크 외곽선(가장 큰 연결 성분)을 Visvalingam–Whyatt로 단순화한
      '실제 모양 그대로의' 단순 폴리곤을 충돌 둘레로 사용하고,
      귀 자르기(ear clipping) 삼각분할로 볼록 조각(hull_indices)을 만들어
      SAT 충돌에 참여시킨다.
      → 투명한(비어 있는) 영역은 충돌하지 않고, 패인 홈 안에
        다른 물체가 들어갈 수 있다.
      모든 외곽 엣지에는 외부 노말(edge_normal)을 부여해 CCD 방향이
      명확하다 (벽 통과 방지).
      외곽선이 비정상(자기교차 등)이면 볼록 껍질로 자동 폴백.
    """
    MAX_OUTLINE_POINTS = 20

    def __init__(self, x, y, width, height, image_path):
        super().__init__()
        self.name = "ImageBlock"
        self.color = (200, 200, 200)
        img = pygame.image.load(image_path).convert_alpha()
        self.image = pygame.transform.smoothscale(img, (int(width), int(height)))

        # ── 전경 마스크 생성 (알파 또는 색상 분리) ───────────────────────
        # ★ 이 마스크는 충돌 형상 추출 + 화면 표시 둘 다에 쓴다.
        #   배경이 불투명한 이미지(스크린샷 등)는 색 분리로 잡은 배경을
        #   화면에서도 투명 처리해, '보이는 모양 = 충돌하는 모양'을 보장한다.
        #   (이전엔 회색 배경까지 그려져 빈 영역이 물체와 겹쳐 보였다.)
        fg_mask = _build_foreground_mask(self.image)
        self._apply_mask_transparency(fg_mask)

        # ── 1. 마스크 → 가장 큰 연결 성분 → 외곽선 링 ───────────────────
        ring = None
        tri_indices = None
        try:
            mask = fg_mask
            comps = mask.connected_components()
            if comps:
                mask = max(comps, key=lambda m: m.count())
            outline = mask.outline(every=2)
            if len(outline) >= 3:
                # ── 2. 단순화 (실제 모양 유지, 점 수 제한) ───────────────
                simp = _simplify_ring(outline, self.MAX_OUTLINE_POINTS)
                if len(simp) >= 3 and abs(_signed_area(simp)) > 4.0:
                    # ── 3. 대수적 CCW로 정렬 (노말/삼각분할 일관성) ──────
                    if _signed_area(simp) < 0:
                        simp.reverse()
                    # ── 4. 볼록이면 단일 조각, 오목이면 귀 자르기 삼각분할 ──
                    if _is_convex_ring(simp):
                        ring, tri_indices = simp, [tuple(range(len(simp)))]
                    else:
                        tris = _ear_clip(simp)
                        if tris:
                            ring, tri_indices = simp, tris
        except Exception as e:
            print(f"[ImageBlock] 외곽선 추출 실패: {e}")

        # ── 폴백 1: 볼록 껍질 ────────────────────────────────────────────
        if ring is None:
            try:
                mask = fg_mask
                comps = mask.connected_components()
                if comps:
                    mask = max(comps, key=lambda m: m.count())
                hull = _convex_hull(mask.outline(every=2))
                if len(hull) > self.MAX_OUTLINE_POINTS:
                    step = len(hull) / float(self.MAX_OUTLINE_POINTS)
                    hull = [hull[int(i * step)] for i in range(self.MAX_OUTLINE_POINTS)]
                if len(hull) >= 3:
                    if _signed_area(hull) < 0:
                        hull.reverse()
                    ring = hull
                    tri_indices = [tuple(range(len(hull)))]  # 볼록 → 단일 조각
                    print("[ImageBlock] 오목 분할 실패 → 볼록 껍질 폴백")
            except Exception:
                pass

        # ── 폴백 2: 이미지 전체 사각형 ──────────────────────────────────
        if ring is None:
            w_i, h_i = int(width), int(height)
            ring = [(0, 0), (w_i, 0), (w_i, h_i), (0, h_i)]  # 부호면적 양수(대수적 CCW)
            tri_indices = [(0, 1, 2, 3)]
            print("[ImageBlock] 사각형 폴백")

        # ── 4.5. 긴 엣지 세분화 (둘레 파티클 간격 균일화) ────────────────
        # ★ 평평한 변(예: 위쪽)이 점 2개뿐이면 그 사이 간격이 100px+ 가 되어
        #   얇은 물체가 둘레 파티클 사이로 빠진다(터널링). 일정 간격마다
        #   중간 점을 삽입해 어떤 얇은 물체도 막히도록 한다. 세분화 후
        #   삼각분할도 다시 수행한다.
        MAX_EDGE = 30.0   # 둘레 점 간 최대 간격(px) — 터널링 방지는 강체복원이 보강
        dense = []
        n_ring = len(ring)
        for i in range(n_ring):
            ax, ay = ring[i]
            bx, by = ring[(i + 1) % n_ring]
            dense.append((ax, ay))
            seg = math.hypot(bx - ax, by - ay)
            if seg > MAX_EDGE:
                steps = int(seg // MAX_EDGE)
                for s in range(1, steps + 1):
                    t = s / (steps + 1)
                    dense.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        if len(dense) >= 3 and len(dense) != len(ring):
            ring = dense
            if _signed_area(ring) < 0:
                ring.reverse()
            if _is_convex_ring(ring):
                tri_indices = [tuple(range(len(ring)))]
            else:
                tris = _ear_clip(ring)
                tri_indices = tris if tris else [tuple(range(len(ring)))]

        # ── 5. 파티클 구성 (particles[0]=중심, 이후 둘레 ring) ──────────
        # 둘레 파티클 반경 5px: 다른 도형(Box/Tri=5)과 맞춰 면-면 접촉 감지 안정화
        cx, cy = width / 2, height / 2
        center_p = Particle(x, y, radius=5)
        self.particles.append(center_p)
        self.ref_p1 = center_p

        perim = []
        for px, py in ring:
            p = Particle(x + (px - cx), y + (py - cy), radius=5)
            self.particles.append(p)
            perim.append(p)
        self.ref_p2 = perim[0]

        # ★ 충돌/선택용 고정 둘레 목록 (attach로 파티클이 추가돼도 불변)
        self.render_particles = perim
        # ★ 삼각분할 조각 → collision.get_convex_hulls가 SAT에 사용
        self.hull_indices = [list(t) for t in tri_indices]

        # ── 6. 외곽 솔리드 엣지 ─────────────────────────────────────────
        # ★ edge_normal을 고정 저장하지 않고 'dynamic' 플래그만 단다.
        #   엔진이 매 프레임 폴리곤 중심 기준으로 외부 노말을 재계산하므로
        #   회전/스케일 후에도 노말이 항상 정확하다 (관통 버그 수정).
        n = len(perim)
        for i in range(n):
            p1 = perim[i]
            p2 = perim[(i + 1) % n]
            c = Constraint(p1, p2, is_solid=True)
            c.outward_dynamic = True   # 엔진이 동적으로 외부 노말 계산
            self.constraints.append(c)

        # ── 7. 내부 브레이싱 (최소) ──────────────────────────────────────
        # ★ 형상 유지는 apply_rigid_match(매 프레임 강체 복원)가 담당하므로
        #   내부 constraint는 최소만 둔다. 과도한 brace는 성능만 깎는다.
        #   중심-둘레 연결만으로 충분 (복원이 나머지를 보장).
        for p in perim:
            self.constraints.append(Constraint(center_p, p, is_solid=False))

        self.assign_parents()
        dx = self.ref_p2.pos.x - self.ref_p1.pos.x
        dy = self.ref_p2.pos.y - self.ref_p1.pos.y
        self.base_angle = math.degrees(math.atan2(dy, dx))

        # ── 8. 강체 rest shape 저장 (자체 shape-matching용) ──────────────
        # 충돌 후 둘레가 변형돼도 이 rest shape로 복원해 강체를 유지한다.
        # rest_offset = (생성 시점) 파티클 위치 - 무게중심
        self._rigid_capture_rest()

    def _rigid_capture_rest(self):
        """현재 파티클 배치를 강체 rest shape으로 캡처."""
        ps = self.particles
        n = len(ps)
        cx = sum(p.pos.x for p in ps) / n
        cy = sum(p.pos.y for p in ps) / n
        c = pygame.math.Vector2(cx, cy)
        self._rigid_rest = [(p, p.pos - c) for p in ps]

    def apply_rigid_match(self):
        """COM 기반 shape-matching으로 모든 파티클을 rest shape에 맞춰 강체 복원.
        Verlet 속도(old_pos)도 같은 변위로 옮겨 속도를 보존한다.
        정적 파티클이 있으면 복원하지 않는다(고정 ImageBlock은 그대로 둠)."""
        rest = getattr(self, '_rigid_rest', None)
        if not rest:
            return
        ps = [p for p, _ in rest]
        if any(p.is_static for p in ps):
            return
        n = len(ps)
        if n < 3:
            return
        # 현재 무게중심
        cx = sum(p.pos.x for p in ps) / n
        cy = sum(p.pos.y for p in ps) / n
        com = pygame.math.Vector2(cx, cy)
        # 최적 회전각 (Müller et al. shape matching의 2D 폐형식)
        Axx = Axy = Ayx = Ayy = 0.0
        for p, r in rest:
            if r.length_squared() < 1e-6:
                continue
            q = p.pos - com
            Axx += q.x * r.x; Axy += q.x * r.y
            Ayx += q.y * r.x; Ayy += q.y * r.y
        denom = Axx + Ayy
        if abs(denom) < 1e-8 and abs(Ayx - Axy) < 1e-8:
            theta = 0.0
        else:
            theta = math.atan2(Ayx - Axy, denom)
        cos_t = math.cos(theta); sin_t = math.sin(theta)
        for p, r in rest:
            tx = com.x + cos_t * r.x - sin_t * r.y
            ty = com.y + sin_t * r.x + cos_t * r.y
            delta = pygame.math.Vector2(tx - p.pos.x, ty - p.pos.y)
            p.pos += delta
            p.old_pos += delta   # 속도 보존

    def _apply_mask_transparency(self, mask):
        """전경 마스크(0=배경) 기준으로 self.image의 배경 픽셀을 투명화.
        충돌 형상과 화면 표시 형상을 일치시킨다.
        마스크가 거의 전부(>97%) 전경이면(원래 투명 PNG) 손대지 않는다."""
        try:
            w, h = self.image.get_size()
            total = w * h
            if mask.count() >= 0.97 * total:
                return  # 이미 알파가 있는 정상 PNG — 변형 불필요
            # 마스크를 흰(전경)/검(배경) 알파 서피스로 변환 후
            # BLEND_RGBA_MULT로 배경 알파를 0으로 (픽셀 루프보다 훨씬 빠름)
            self.image = self.image.convert_alpha()
            alpha_surf = mask.to_surface(
                setcolor=(255, 255, 255, 255),
                unsetcolor=(255, 255, 255, 0))
            self.image.blit(alpha_surf, (0, 0),
                            special_flags=pygame.BLEND_RGBA_MULT)
        except Exception as e:
            print(f"[ImageBlock] 배경 투명화 실패: {e}")

    def get_angle(self):
        dx = self.ref_p2.pos.x - self.ref_p1.pos.x
        dy = self.ref_p2.pos.y - self.ref_p1.pos.y
        return math.degrees(math.atan2(dy, dx)) - self.base_angle

    def collision_centroid(self):
        """충돌 외부 노말 계산용 둘레 무게중심 (현재 위치 기준)."""
        rp = self.render_particles
        cx = sum(p.pos.x for p in rp) / len(rp)
        cy = sum(p.pos.y for p in rp) / len(rp)
        return pygame.math.Vector2(cx, cy)

    def get_size(self):
        rp = self.render_particles
        xs = [p.pos.x for p in rp]
        ys = [p.pos.y for p in rp]
        return max(xs) - min(xs), max(ys) - min(ys)