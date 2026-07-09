import pygame
from objects import Circle, Particle, Constraint, StringObj, TrueSpring, ImageBlock

# ─────────────────────────────────────────────────────────────────────────────
# 물리 상수 (전역 기본값)
# ─────────────────────────────────────────────────────────────────────────────
AIR_DRAG_COEFF      = 0.0008   # 전역 공기저항 기본값 (속도² 비례)
ROLLING_DRAG_COEFF  = 0.002    # 원형 물체 구름 마찰 선형 감쇠
GRAVITY_DEFAULT     = 900.0    # px/s²

# XPBD 관련 상수
# constraint iteration 수를 substep에 따라 자동 조정하는 기반값
BASE_CONSTRAINT_ITER = 20      # substep=1일 때 기본 iteration
MAX_CONSTRAINT_ITER  = 60      # 최대 iteration 상한 (성능 보호)

# 용수철 weld 회전/축 구속의 '완화 계수'.
#   1.0이면 매 프레임 강제로 축에 갖다 놓아 충돌 보정을 덮어써 벽끼임 등
#   셀프버그가 난다. <1.0이면 부분 보정 → 충돌이 밀어낸 위치를 존중하면서
#   몇 프레임에 걸쳐 수렴(충돌 없을 땐 거의 즉시 정렬됨).
SPRING_WELD_RELAX = 0.5

# ─────────────────────────────────────────────────────────────────────────────
# SAT 폴리곤 충돌 헬퍼 → collision.py 모듈로 분리됨
#   ★ sat_collide_objects: 오목 도형(HShape/TShape/PolygonShape)을
#     볼록 조각(box_groups / hull_indices)으로 분해해 정확히 충돌 검사
# ─────────────────────────────────────────────────────────────────────────────
from collision import (_sat_project, _sat_overlap, _sat_test,
                       _segment_intersect, _poly_get_verts,
                       sat_collide_objects)


def _edge_outward_normal(c):
    """엣지 c의 외부(바깥) 단위 노말을 반환. 없으면 None.

    ★ outward_dynamic 플래그가 있는 엣지(ImageBlock 둘레)는 부모 도형의
      현재 무게중심을 기준으로 매 프레임 외부 방향을 재계산한다.
      → 회전/스케일 후에도 노말이 항상 정확해 관통이 발생하지 않는다.
    그 외 엣지는 기존 고정 edge_normal(있으면)을 그대로 사용한다.
    """
    if getattr(c, 'outward_dynamic', False):
        parent = getattr(c, 'parent', None)
        if parent is not None and not isinstance(parent, str) and \
           hasattr(parent, 'collision_centroid'):
            mid = (c.p1.pos + c.p2.pos) * 0.5
            out = mid - parent.collision_centroid()
            l = out.length()
            if l > 1e-9:
                return (out.x / l, out.y / l)
        # 부모를 못 찾으면 고정 노말로 폴백
    return getattr(c, 'edge_normal', None)


class PhysicsEngine:
    def __init__(self, width, height):
        self.width  = width
        self.height = height
        self.gravity         = pygame.math.Vector2(0, GRAVITY_DEFAULT)
        self.gravity_enabled = True
        self.objects = []
        self.global_constraints = []
        self.pulley_constraints = []
        self.constraint_iterations = BASE_CONSTRAINT_ITER
        self.snapshot = []
        self.enable_spring_collision  = True
        self.enable_attach_collision  = True
        self.last_dt = 0.0
        self._current_substeps = 1  # main.py에서 매 프레임 갱신

        self.air_drag_coeff     = AIR_DRAG_COEFF
        self.rolling_drag_coeff = ROLLING_DRAG_COEFF

        # ── 수직항력 누산기 (프레임당 리셋, substep 누적) ─────────────────
        # _contact_normal_impulse[id(p)] = 총 법선 충격량 합 (Vector2)
        self._contact_normal_impulse = {}
        self._weld_member_ids = set()

    # ── 스냅샷 ─────────────────────────────────────────────────────────────────
    def save_snapshot(self):
        self.snapshot = []
        for obj in self.objects:
            for p in obj.particles:
                self.snapshot.append((p, p.pos.copy(), p.old_pos.copy()))

    def load_snapshot(self):
        if hasattr(self, 'snapshot') and self.snapshot:
            for p, pos, old_pos in self.snapshot:
                p.pos = pos.copy()
                p.old_pos = old_pos.copy()

    # ── 오브젝트/제약 관리 ─────────────────────────────────────────────────────
    def add_object(self, obj):             self.objects.append(obj)
    def add_global_constraint(self, c):   self.global_constraints.append(c)
    def add_pulley_constraint(self, pc):  self.pulley_constraints.append(pc)

    def remove_object(self, obj):
        if obj in self.objects: self.objects.remove(obj)
        particles_set = set(obj.particles)
        dead_pcs = [pc for pc in self.pulley_constraints
                    if any(p in particles_set for p in pc.pts)]
        if dead_pcs:
            extra_objs = set()
            for pc in dead_pcs:
                for p in pc.pts:
                    if p not in particles_set and p.parent and p.parent in self.objects:
                        extra_objs.add(p.parent)
            for extra in extra_objs:
                if extra in self.objects:
                    self.objects.remove(extra)
                    particles_set |= set(extra.particles)
        self.global_constraints = [c for c in self.global_constraints
                                   if c.p1 not in particles_set and c.p2 not in particles_set]
        self.pulley_constraints  = [pc for pc in self.pulley_constraints
                                   if not any(p in particles_set for p in pc.pts)]
        # weld rest shapes 재계산 (제거된 오브젝트 포함 그룹 갱신)
        self._rebuild_weld_rest_shapes()

    # ── 수직항력 impulse 누산 헬퍼 ────────────────────────────────────────────
    def _accum_normal_impulse(self, p, normal_vec, impulse_mag):
        """접촉 법선 방향으로 가해진 충격량을 누적 (수직항력 계산용)."""
        pid = id(p)
        if pid not in self._contact_normal_impulse:
            self._contact_normal_impulse[pid] = 0.0
        self._contact_normal_impulse[pid] += impulse_mag

    # ── XPBD stiffness 보정 ────────────────────────────────────────────────────
    @staticmethod
    def _xpbd_alpha(stiffness, dt):
        """
        XPBD 호환 compliance: α = 1/(k·dt²)
        stiffness=1.0(완전 구속), stiffness<1.0(탄성)
        반환: 보정된 compliance (α)
        """
        if stiffness >= 1.0:
            return 0.0   # 완전 구속: compliance 0
        k = max(stiffness, 1e-6)
        # 탄성 상수를 적절히 스케일 (stiffness 0.001 → 부드러운 스프링)
        spring_k = k * 1e6
        return 1.0 / (spring_k * max(dt * dt, 1e-10))

    # ── 충돌 억제 쌍 수집 헬퍼 ───────────────────────────────────────────────
    def _build_no_collision_set(self):
        """no_collision=True 인 global constraint 양쪽 오브젝트 쌍 집합을 반환.
        반환: set of frozenset({id(objA), id(objB)})
        """
        nc = set()
        for c in self.global_constraints:
            if not getattr(c, 'no_collision', False): continue
            objA = getattr(c.p1, 'parent', None)
            objB = getattr(c.p2, 'parent', None)
            if objA and objB and objA is not objB:
                nc.add(frozenset((id(objA), id(objB))))
        return nc

    # ── 파티클-파티클 탄성 반발 (공통 코어) ───────────────────────────────────
    def _resolve_particle_pair_restitution(self, p1, p2, dt, no_col_set=None):
        """두 파티클 사이 충돌 반발. 위치 보정 없이 old_pos만 수정."""
        if p1.is_static and p2.is_static: return
        if _same_group(p1, p2): return
        if _different_layer(p1, p2): return
        # weld 그룹 내부 skip
        wg1 = getattr(getattr(p1, 'parent', None), 'weld_group_id', None)
        wg2 = getattr(getattr(p2, 'parent', None), 'weld_group_id', None)
        if wg1 is not None and wg1 == wg2: return
        # no_collision 억제 쌍 검사
        if no_col_set:
            objA = getattr(p1, 'parent', None)
            objB = getattr(p2, 'parent', None)
            if objA and objB and frozenset((id(objA), id(objB))) in no_col_set:
                return

        delta    = p1.pos - p2.pos
        dist     = delta.length()
        min_dist = p1.radius + p2.radius
        if dist >= min_dist or dist < 1e-6: return

        normal  = delta / dist
        inv_m1  = 0.0 if p1.is_static else 1.0 / p1.mass
        inv_m2  = 0.0 if p2.is_static else 1.0 / p2.mass
        total_w = inv_m1 + inv_m2
        if total_w < 1e-10: return

        vel1    = p1.pos - p1.old_pos
        vel2    = p2.pos - p2.old_pos
        rel_v_n = (vel1 - vel2).dot(normal)
        if rel_v_n >= 0: return

        e1 = getattr(getattr(p1, 'parent', None), 'restitution', 0.5)
        e2 = getattr(getattr(p2, 'parent', None), 'restitution', 0.5)
        e  = (e1 * e2) ** 0.5
        # weld 그룹 파티클은 개별 반발 억제 (강체 재투영이 처리)
        if id(p1) in self._weld_member_ids or id(p2) in self._weld_member_ids:
            e = 0.0
        j  = -(1.0 + e) * rel_v_n / total_w

        if not p1.is_static:
            p1.old_pos -= normal * (j * inv_m1)
            self._accum_normal_impulse(p1, normal, j * inv_m1)
        if not p2.is_static:
            p2.old_pos += normal * (j * inv_m2)
            self._accum_normal_impulse(p2, normal, j * inv_m2)

    def _apply_restitution_inline(self, all_particles, dt):
        """Verlet 직후 substep 내 탄성 반발."""
        nc = self._build_no_collision_set()
        n = len(all_particles)
        for i in range(n):
            for j in range(i + 1, n):
                self._resolve_particle_pair_restitution(all_particles[i], all_particles[j], dt, nc)

    def apply_restitution(self):
        """프레임당 1회 호출 (main.py 호환)."""
        nc = self._build_no_collision_set()
        all_particles = [p for obj in self.objects for p in obj.particles]
        for i in range(len(all_particles)):
            for j in range(i + 1, len(all_particles)):
                self._resolve_particle_pair_restitution(all_particles[i], all_particles[j],
                                                        max(self.last_dt, 1e-4), nc)

    def weld_objects(self, obj1, obj2, pos1=None, pos2=None):
        if obj1 == obj2: return
        # ★ weld_group_id 미초기화 객체 방어 (생성 직후 첫 update 전에 weld하는 경우)
        for o in self.objects:
            if not hasattr(o, 'weld_group_id'):
                o.weld_group_id = o.collision_group
        if not hasattr(self, '_spring_anchors'):
            # id(스프링 끝점 파티클) → 글루 대상 오브젝트
            #   스프링은 강체 프레임에 '병합'되지 않고, 클릭한 끝점만 대상
            #   오브젝트의 프레임에 붙는다(glue). 반대쪽 끝점과 spring constraint는
            #   자유롭게 남아 수축/압축(탄성)이 유지된다.
            self._spring_anchors = {}
        if not hasattr(self, '_spring_weld_axis'):
            # id(고정 끝점) → (free_ep, target, ref0_pid, ref1_pid, a, b)
            #   한쪽만 weld된 용수철의 '용접 방향'을 대상 프레임 로컬좌표로 저장.
            #   매 프레임 이 방향으로 자유 끝점을 정렬 → 자유회전(옆흔들림) 차단,
            #   축방향 압축/팽창만 허용.
            self._spring_weld_axis = {}
        if not hasattr(self, '_spring_both_axis'):
            # id(spring) → (epA_pid, objA, epB_pid, objB, ax, ay)
            #   양끝이 각각 다른 물체에 weld된 용수철. 두 끝점이 '용접 축'과
            #   평행을 유지하도록(회전 금지) 두 물체를 옆방향으로 보정.
            #   축방향(압축/팽창)은 spring constraint가 그대로 담당.
            self._spring_both_axis = {}

        is_spring1 = getattr(obj1, 'name', '') == 'Spring'
        is_spring2 = getattr(obj2, 'name', '') == 'Spring'

        def _nearest_ep(spring, pos):
            eps = spring.particles[:2]
            if not eps: return None
            if pos is None or len(eps) < 2:
                return eps[0]
            return min(eps, key=lambda ep: ep.pos.distance_squared_to(pos))

        def _merge_collision_only(a, b):
            """충돌만 같은 그룹으로 통일(서로 충돌 안 함). 강체(weld) 프레임은 합치지 않음."""
            old_cg = a.collision_group
            new_cg = b.collision_group
            if old_cg == new_cg: return
            for o in self.objects:
                if o.collision_group == old_cg:
                    o.collision_group = new_cg

        # ── ① 스프링이 끼는 weld ─────────────────────────────────────────────
        if is_spring1 or is_spring2:
            if is_spring1 and is_spring2:
                # 스프링-스프링: 클릭한 두 끝점을 0거리 강결합으로 핀 (둘 다 탄성 유지)
                ep1 = _nearest_ep(obj1, pos1)
                ep2 = _nearest_ep(obj2, pos2)
                if ep1 is not None and ep2 is not None:
                    self.add_global_constraint(
                        Constraint(ep1, ep2, length=0, stiffness=1.0, style="hinge"))
                _merge_collision_only(obj1, obj2)
            else:
                spring = obj1 if is_spring1 else obj2
                target = obj2 if is_spring1 else obj1
                spos   = pos1 if is_spring1 else pos2
                tpos   = pos2 if is_spring1 else pos1
                ep = _nearest_ep(spring, spos)
                if ep is not None:
                    # 클릭한 끝점을 대상 오브젝트에 글루 (강체 병합 아님)
                    self._spring_anchors[id(ep)] = target
                    # 회전 구속: 용접 당시 용접 방향을 대상 프레임 기준으로 저장
                    free_ep = next((q for q in spring.particles[:2] if q is not ep), None)
                    if free_ep is not None:
                        self._capture_spring_weld_axis(ep, free_ep, target)
                        # ── 반대쪽 끝점이 이미 weld돼 있으면 → '양끝 weld'. ──
                        #   두 물체를 강체로 병합하지 않는다(병합하면 스프링이
                        #   얼어 압축/팽창 불가). 양 끝점을 각자 물체에 글루만
                        #   해두면, 스프링은 두 끝점 사이에서 자유롭게 압축/팽창
                        #   한다. flop(각 물체가 끝점 중심으로 회전)은 shape
                        #   matching에서 끝점을 '회전 fit'에서 제외해 방지한다.
                        if id(free_ep) in self._spring_anchors:
                            pass  # 글루는 위에서 이미 완료, 추가 처리 불필요
                    # 폭발 방지: 끝점 속도를 대상 오브젝트 평균 속도에 맞춤
                    tparts = [p for p in target.particles if not p.is_static]
                    if tparts:
                        tm = sum(p.mass for p in tparts)
                        if tm > 1e-10:
                            tvel = sum(((p.pos - p.old_pos) * p.mass for p in tparts),
                                       pygame.math.Vector2()) / tm
                            ep.old_pos = ep.pos - tvel
                _merge_collision_only(spring, target)
            self._rebuild_weld_rest_shapes()
            return

        # ── ② 둘 다 비-스프링: 기존 강체 weld (병합) ────────────────────────
        old_group    = obj2.collision_group
        target_group = obj1.collision_group
        old_wgid     = getattr(obj2, 'weld_group_id', id(obj2))
        target_wgid  = getattr(obj1, 'weld_group_id', id(obj1))
        for obj in self.objects:
            if obj.collision_group == old_group:
                obj.collision_group = target_group
            if getattr(obj, 'weld_group_id', id(obj)) == old_wgid:
                obj.weld_group_id = target_wgid

        # ── 속도 통일: 두 그룹의 질량 가중 평균 속도로 모든 파티클 동기화 ──
        # weld 순간 속도 차이로 인한 충격/폭발 방지
        wgid = target_wgid
        group_particles = [
            p for obj in self.objects
            if getattr(obj, 'weld_group_id', None) == wgid
            for p in obj.particles
            if not p.is_static
        ]
        if group_particles:
            total_mass = sum(p.mass for p in group_particles)
            if total_mass > 1e-10:
                avg_vel = sum(
                    ((p.pos - p.old_pos) * p.mass for p in group_particles),
                    pygame.math.Vector2()
                ) / total_mass
                for p in group_particles:
                    p.old_pos = p.pos - avg_vel

        # ── Shape-Matching 강체 결합 ──────────────────────────────────────
        self._rebuild_weld_rest_shapes()

    def _rebuild_weld_rest_shapes(self):
        """
        weld_group_id 별 rigid frame(rest shape)을 (재)계산.
        self._weld_rest: { weld_group_id: [ (particle, local_offset_Vector2) ] }
        local_offset = 파티클 위치 - 프레임 무게중심  (현재 시점 기준)

        ★ 스프링 처리:
          - 스프링은 강체 프레임에 '통째로' 들어가지 않는다(들어가면 양 끝이
            고정돼 탄성 소멸).
          - 대신 weld 시 클릭한 끝점만 _spring_anchors[id(ep)] = 대상오브젝트 로
            기록해 두고, 그 끝점을 '대상 오브젝트의 프레임'에 멤버로 추가한다.
            → 끝점은 대상에 단단히 붙고(고정), 반대쪽 끝점 + spring constraint는
              자유로워 수축/압축(탄성)이 유지된다.
          - 양 끝을 서로 다른 두 물체에 weld하면 두 물체는 각자의 프레임으로
            분리된 채 스프링으로만 연결돼, 용수철-질량 진동이 정상 동작한다.
        """
        if not hasattr(self, '_weld_rest'):
            self._weld_rest = {}
        if not hasattr(self, '_spring_anchors'):
            self._spring_anchors = {}

        # ── 1) 비-스프링 오브젝트만으로 강체 그룹(rigid frame) 구성 ──────────
        rigid_groups   = {}   # wgid → [particle]   (스프링 제외)
        wgid_to_objs   = {}   # wgid → set(id(비-스프링 obj))
        for obj in self.objects:
            if getattr(obj, 'name', '') == 'Spring':
                continue
            wgid = getattr(obj, 'weld_group_id', None)
            if wgid is None: continue
            rigid_groups.setdefault(wgid, []).extend(obj.particles)
            wgid_to_objs.setdefault(wgid, set()).add(id(obj))

        # ── 2) 글루된 스프링 끝점을 대상 오브젝트의 그룹에 추가 ──────────────
        #   (삭제된 스프링/대상은 정리)
        alive_pid_to_p = {}
        for obj in self.objects:
            for p in obj.particles:
                alive_pid_to_p[id(p)] = p
        extra_by_wgid = {}   # wgid → [endpoint particle]
        valid_anchors = {}
        for ep_pid, target in list(self._spring_anchors.items()):
            ep = alive_pid_to_p.get(ep_pid)
            if ep is None:            continue   # 스프링 끝점 삭제됨
            if target not in self.objects: continue  # 대상 삭제됨
            twgid = getattr(target, 'weld_group_id', None)
            if twgid is None:         continue
            valid_anchors[ep_pid] = target
            extra_by_wgid.setdefault(twgid, []).append(ep)
        self._spring_anchors = valid_anchors

        # ── 3) 최종 rest shape 등록 ─────────────────────────────────────────
        self._weld_rest = {}
        for wgid in set(rigid_groups) | set(extra_by_wgid):
            base  = rigid_groups.get(wgid, [])
            extra = extra_by_wgid.get(wgid, [])
            members = list(base) + list(extra)
            if not members:
                continue
            # 등록 조건: 여러 오브젝트가 묶인 강체 그룹(기존 동작) 또는
            #            스프링 끝점이 글루된 그룹(단일 오브젝트라도 끝점을 끌고감)
            multi = len(wgid_to_objs.get(wgid, set())) >= 2
            if not multi and not extra:
                continue
            cx = sum(p.pos.x for p in members) / len(members)
            cy = sum(p.pos.y for p in members) / len(members)
            center = pygame.math.Vector2(cx, cy)
            self._weld_rest[wgid] = [
                (p, p.pos - center) for p in members
            ]

    def _capture_spring_weld_axis(self, fixed_ep, free_ep, target):
        """용접 순간의 '용접 방향'(fixed→free)을 대상 오브젝트의 로컬 프레임
        좌표 (a, b)로 저장. 대상이 회전하면 그 회전을 따라 방향이 돌아간다.
        대상에 회전 기준(파티클 2개)이 없으면(Circle 등) 월드 고정 방향으로 저장."""
        if not hasattr(self, '_spring_weld_axis'):
            self._spring_weld_axis = {}
        tparts = target.particles
        ref0 = ref1 = None
        if len(tparts) >= 2:
            ref0 = min(tparts, key=lambda p: p.pos.distance_squared_to(fixed_ep.pos))
            ref1 = max(tparts, key=lambda p: p.pos.distance_squared_to(ref0.pos))
            if ref1 is ref0 or ref0.pos.distance_to(ref1.pos) < 1e-3:
                ref0 = ref1 = None
        wdir = free_ep.pos - fixed_ep.pos      # 용접 당시 방향(world)
        if ref0 is not None and ref1 is not None:
            e1 = ref1.pos - ref0.pos
            e1 = e1 / e1.length()
            e2 = pygame.math.Vector2(-e1.y, e1.x)
            self._spring_weld_axis[id(fixed_ep)] = (
                free_ep, target, id(ref0), id(ref1), wdir.dot(e1), wdir.dot(e2))
        else:
            # 회전 기준 없음 → 월드 고정 방향 (ref pid = None)
            self._spring_weld_axis[id(fixed_ep)] = (
                free_ep, target, None, None, wdir.x, wdir.y)

    def _apply_spring_weld_orientation(self):
        """한쪽만 weld된 용수철의 자유 끝점을 '용접 방향' 축에 정렬한다.
        → 축방향 길이 변화(압축/팽창)는 그대로 두고, 옆으로 흔들리는
          자유 회전만 제거한다. 대상이 회전하면 축도 함께 회전한다.
        양쪽 끝이 모두 weld된 용수철(_spring_anchors에 둘 다 존재)은 건너뛴다."""
        swa = getattr(self, '_spring_weld_axis', None)
        if not swa:
            return
        anchors = getattr(self, '_spring_anchors', {})
        pid_to_p = {}
        for obj in self.objects:
            for p in obj.particles:
                pid_to_p[id(p)] = p
        dead = []
        for fep_pid, data in swa.items():
            free_ep, target, ref0_pid, ref1_pid, a, b = data
            fixed_ep = pid_to_p.get(fep_pid)
            # 정리 대상: 끝점/대상 삭제됐거나, 더 이상 글루 상태가 아님
            if fixed_ep is None or free_ep is None or target not in self.objects \
               or fep_pid not in anchors:
                dead.append(fep_pid); continue
            if free_ep.is_static:
                continue
            # 양쪽 다 weld된 경우(두 끝 모두 글루) → 방향은 두 프레임이 결정하므로 skip
            if id(free_ep) in anchors:
                continue
            # 용접 방향(world): 대상 프레임 회전을 따라감
            if ref0_pid is not None and ref1_pid is not None:
                ref0 = pid_to_p.get(ref0_pid); ref1 = pid_to_p.get(ref1_pid)
                if ref0 is None or ref1 is None:
                    dead.append(fep_pid); continue
                e1 = ref1.pos - ref0.pos
                el = e1.length()
                if el < 1e-6:
                    axis = pygame.math.Vector2(a, b)
                else:
                    e1 = e1 / el
                    e2 = pygame.math.Vector2(-e1.y, e1.x)
                    axis = e1 * a + e2 * b
            else:
                axis = pygame.math.Vector2(a, b)   # 월드 고정
            al = axis.length()
            if al < 1e-8:
                continue
            axis_u = axis / al
            # 현재 길이 유지(축방향 압축/팽창 허용), 방향만 축으로 정렬
            cur_len = (free_ep.pos - fixed_ep.pos).length()
            if cur_len < 1e-6:
                continue
            new_pos = fixed_ep.pos + axis_u * cur_len
            # 완화(relaxation): 한 번에 강제로 끌어오지 않고 부분 보정한다.
            #   → 충돌이 밀어낸 위치를 존중(벽끼임 셀프버그 방지). pos만 lerp
            #     하므로 옆흔들림 속도도 함께 감쇠되고, 축방향(거리) 성분은 그대로.
            free_ep.pos = free_ep.pos.lerp(new_pos, SPRING_WELD_RELAX)
            self._clamp_to_world(free_ep)   # 벽 밖/안으로 강제되지 않도록
        for k in dead:
            swa.pop(k, None)

    def _clamp_to_world(self, p):
        """파티클을 화면 경계 안으로 가둔다(위치만). 보정으로 벽 안에 박히는
        것을 방지. 속도는 건드리지 않아 충돌 반발과 충돌하지 않는다."""
        if p.is_static:
            return
        r = getattr(p, 'radius', 0) or 0
        if p.pos.x < r:                 p.pos.x = r
        elif p.pos.x > self.width - r:  p.pos.x = self.width - r
        if p.pos.y < r:                 p.pos.y = r
        elif p.pos.y > self.height - r: p.pos.y = self.height - r

    @staticmethod
    def _box_two_refs(o):
        """오브젝트의 회전을 측정할 떨어진 두 파티클 반환 (없으면 None,None)."""
        ps = o.particles
        if len(ps) < 2:
            return None, None
        a = ps[0]
        b = max(ps, key=lambda p: p.pos.distance_squared_to(a.pos))
        if a is b or a.pos.distance_to(b.pos) < 1e-3:
            return None, None
        return a, b

    @staticmethod
    def _ang(a, b):
        import math as _math
        d = b.pos - a.pos
        return _math.atan2(d.y, d.x)

    def _merge_weld_groups(self, a, b):
        """두 물체 a, b를 하나의 강체 weld 그룹으로 병합(양끝 weld 용수철용).
        b가 속한 weld 그룹 전체를 a의 그룹으로 합치고, 충격 폭발을 막기 위해
        그룹 전체 속도를 질량가중 평균으로 통일한다. → 전체가 강체로 자연
        회전(질량에 따라 기울어짐)하고 따로 flop하지 않으며 모든 도형에 안정."""
        a_wgid = getattr(a, 'weld_group_id', id(a))
        b_wgid = getattr(b, 'weld_group_id', id(b))
        if a_wgid == b_wgid:
            return
        for obj in self.objects:
            if getattr(obj, 'weld_group_id', id(obj)) == b_wgid:
                obj.weld_group_id = a_wgid
        gp = [p for obj in self.objects
              if getattr(obj, 'weld_group_id', None) == a_wgid
              for p in obj.particles if not p.is_static]
        if gp:
            tm = sum(p.mass for p in gp)
            if tm > 1e-10:
                avg = sum(((p.pos - p.old_pos) * p.mass for p in gp),
                          pygame.math.Vector2()) / tm
                for p in gp:
                    p.old_pos = p.pos - avg

    def _capture_spring_both_axis(self, spring, epA, objA, epB, objB):
        """양끝 weld 용수철: 두 물체의 '상대 방향'만 잠그고(서로 따로 회전 X)
        전체 방향은 물리(충돌·질량)에 따라 자유롭게 회전(텀블)하게 한다.
        축방향 거리만 압축/팽창. (각 물체 오프셋 + 축방향 dir0 저장)"""
        if not hasattr(self, '_spring_both_axis'):
            self._spring_both_axis = {}

        def _com(o):
            return sum((p.pos for p in o.particles), pygame.math.Vector2()) / len(o.particles)

        def _offsets(o):
            c = _com(o)
            return [(id(p), (p.pos.x - c.x, p.pos.y - c.y)) for p in o.particles]

        comA = _com(objA); comB = _com(objB)
        dir0 = comB - comA
        self._spring_both_axis[id(spring)] = {
            'objA': objA, 'objB': objB,
            'epA': id(epA), 'epB': id(epB),
            'offA': _offsets(objA), 'offB': _offsets(objB),
            'dir0': (dir0.x, dir0.y),
        }

    @staticmethod
    def _obj_motion(obj, offsets, pid_to_p):
        """물체의 (회전각 rel, COM, COM속도, 각속도 omega) 측정.
        파티클<2 또는 퍼짐 없음 → rel/omega=None."""
        import math as _math
        ps = [(pid_to_p.get(pid), off) for pid, off in offsets]
        if any(p is None for p, _ in ps):
            return None
        n = len(ps)
        com = sum((p.pos for p, _ in ps), pygame.math.Vector2()) / n
        com_v = sum(((p.pos - p.old_pos) for p, _ in ps), pygame.math.Vector2()) / n
        if n < 2:
            return (None, com, com_v, None)
        Axx = Axy = Ayx = Ayy = 0.0
        L = I = 0.0
        spread = 0.0
        for p, off in ps:
            qx = p.pos.x - com.x; qy = p.pos.y - com.y
            Axx += qx * off[0]; Axy += qx * off[1]
            Ayx += qy * off[0]; Ayy += qy * off[1]
            vx = (p.pos.x - p.old_pos.x) - com_v.x
            vy = (p.pos.y - p.old_pos.y) - com_v.y
            L += qx * vy - qy * vx
            I += qx * qx + qy * qy
            spread += off[0] * off[0] + off[1] * off[1]
        if spread < 1e-6:
            return (None, com, com_v, None)
        rel = _math.atan2(Ayx - Axy, Axx + Ayy)
        omega = (L / I) if I > 1e-9 else 0.0
        return (rel, com, com_v, omega)

    def _apply_spring_both_ends_axis(self):
        """양끝 weld 용수철: 두 물체가 '따로' 회전(flop)하지 못하게 상대 회전
        속도만 감쇠(dissipative→에너지 주입 없음, 무조건 안정)하고, 두 물체가
        함께 도는 공유 회전(텀블)은 그대로 둔다. 위치는 강제 재배치하지 않아
        shape matching과 싸우지 않는다(폭주 없음). + 축 평행(옆흔들림) 정렬.
        축방향 압축/팽창은 spring constraint가 담당. 완화·클램프로 충돌 존중."""
        import math as _math
        sba = getattr(self, '_spring_both_axis', None)
        if not sba:
            return
        pid_to_p = {}
        for obj in self.objects:
            for p in obj.particles:
                pid_to_p[id(p)] = p

        R = SPRING_WELD_RELAX
        dead = []
        for spid, d in sba.items():
            objA = d['objA']; objB = d['objB']
            if objA not in self.objects or objB not in self.objects:
                dead.append(spid); continue
            mtA = self._obj_motion(objA, d['offA'], pid_to_p)
            mtB = self._obj_motion(objB, d['offB'], pid_to_p)
            if mtA is None or mtB is None:
                dead.append(spid); continue
            relA, comA, cvA, omA = mtA
            relB, comB, cvB, omB = mtB

            def _mass(o):
                return sum(p.mass for p in o.particles if not p.is_static)
            mA = _mass(objA); mB = _mass(objB)

            # ── (1) 상대 '회전 드리프트' 위치 보정 (둘이 같은 방향 유지) ──
            #   상대 misalignment를 절반씩 반대로 회전시켜 좁힌다. COM 중심
            #   회전이라 선형운동량 보존. 완화 R로 부드럽게(과보정 방지).
            if relA is not None and relB is not None:
                mis = relA - relB
                while mis > _math.pi:  mis -= 2 * _math.pi
                while mis < -_math.pi: mis += 2 * _math.pi
                tot_m = mA + mB
                if tot_m > 1e-9 and abs(mis) > 1e-5:
                    # 질량 큰 쪽을 덜 움직임
                    corrA = -mis * (mB / tot_m) * R * 0.5
                    corrB = +mis * (mA / tot_m) * R * 0.5
                    self._rotate_about_com(objA, d['offA'], pid_to_p, comA, corrA)
                    self._rotate_about_com(objB, d['offB'], pid_to_p, comB, corrB)

            # ── (2) 상대 '회전 속도' 감쇠 (flop 진동 억제, dissipative) ──
            if omA is not None and omB is not None:
                tot_m = mA + mB
                if tot_m > 1e-9:
                    common = (mA * omA + mB * omB) / tot_m
                    dampA = (common - omA) * 0.5
                    dampB = (common - omB) * 0.5
                    self._add_spin(objA, d['offA'], pid_to_p, comA, dampA)
                    self._add_spin(objB, d['offB'], pid_to_p, comB, dampB)

            # ── (3) 축 평행 유지(옆흔들림 제거): 두 COM을 공유축에 정렬 ──
            shared = 0.0
            if relA is not None or relB is not None:
                sx = sy = 0.0
                if relA is not None and mA > 1e-9:
                    sx += mA*_math.cos(relA); sy += mA*_math.sin(relA)
                if relB is not None and mB > 1e-9:
                    sx += mB*_math.cos(relB); sy += mB*_math.sin(relB)
                if sx*sx+sy*sy > 1e-12:
                    shared = _math.atan2(sy, sx)
            dir0 = pygame.math.Vector2(*d['dir0'])
            cc = _math.cos(shared); ss = _math.sin(shared)
            axis = pygame.math.Vector2(cc*dir0.x - ss*dir0.y, ss*dir0.x + cc*dir0.y)
            if axis.length() < 1e-8:
                continue
            axis_u = axis / axis.length()
            perp = pygame.math.Vector2(-axis_u.y, axis_u.x)
            e = (comB - comA).dot(perp)
            if abs(e) < 1e-9:
                continue
            wA = (1.0/mA) if mA > 1e-9 else 0.0
            wB = (1.0/mB) if mB > 1e-9 else 0.0
            tot = wA + wB
            if tot < 1e-12:
                continue
            moveA = perp * ( e * wA/tot * R)
            moveB = perp * (-e * wB/tot * R)
            for pid, _o in d['offA']:
                p = pid_to_p.get(pid)
                if p is not None and not p.is_static:
                    p.pos += moveA; self._clamp_to_world(p)
            for pid, _o in d['offB']:
                p = pid_to_p.get(pid)
                if p is not None and not p.is_static:
                    p.pos += moveB; self._clamp_to_world(p)
        for k in dead:
            sba.pop(k, None)

    @staticmethod
    def _rotate_about_com(obj, offsets, pid_to_p, com, ang):
        """물체를 COM 중심으로 ang(rad) 회전(pos만). 선형운동량 보존."""
        import math as _math
        if abs(ang) < 1e-6 or all(p.is_static for p in obj.particles):
            return
        cc = _math.cos(ang); ss = _math.sin(ang)
        for pid, _o in offsets:
            p = pid_to_p.get(pid)
            if p is None or p.is_static:
                continue
            rx = p.pos.x - com.x; ry = p.pos.y - com.y
            p.pos.x = com.x + cc*rx - ss*ry
            p.pos.y = com.y + ss*rx + cc*ry

    @staticmethod
    def _add_spin(obj, offsets, pid_to_p, com, dw):
        """물체에 각속도 변화 dw를 부여(old_pos 조정). 상대 스핀 감쇠용."""
        if abs(dw) < 1e-7 or all(p.is_static for p in obj.particles):
            return
        for pid, _o in offsets:
            p = pid_to_p.get(pid)
            if p is None or p.is_static:
                continue
            rx = p.pos.x - com.x; ry = p.pos.y - com.y
            # v += dw × r  →  old_pos -= dw × r
            p.old_pos.x -= (-dw * ry)
            p.old_pos.y -= ( dw * rx)

    def _apply_shape_matching(self):
        """
        weld 그룹별로 Shape-Matching을 수행한다.

        힌지 파티클은 앵커로 취급 — 힌지가 있으면 힌지 파티클 위치를
        기준점으로 삼아 나머지 파티클을 rigid하게 배치한다.
        힌지가 없으면 COM 기반 기존 방식.
        """
        if not hasattr(self, '_weld_rest') or not self._weld_rest:
            return
        import math as _math

        # 힌지 파티클 id 집합
        hinge_pinned = set()
        for c in self.global_constraints:
            if getattr(c, 'style', '') == 'hinge':
                hinge_pinned.add(id(c.p1))
                hinge_pinned.add(id(c.p2))

        for wgid, rest_list in self._weld_rest.items():
            if not rest_list: continue

            particles = [p for p, _ in rest_list]
            offsets   = [r for _, r in rest_list]
            mobile    = [p for p in particles if not p.is_static]
            if not mobile: continue

            pinned_in_group = [p for p in particles if id(p) in hinge_pinned]

            # ── 정적(static) 파티클이 있는 그룹: 정적 파티클을 기준 프레임으로
            #    삼아 고정한다. (글루된 스프링 끝점이 천장 등 정적 물체에 붙은
            #    경우, 끝점이 떠내려가지 않고 단단히 고정된다.) ────────────────
            static_ps = [(p, r) for p, r in rest_list if p.is_static]
            if static_ps:
                s_rest_c = sum((r for _, r in static_ps), pygame.math.Vector2()) / len(static_ps)
                s_cur_c  = sum((p.pos for p, _ in static_ps), pygame.math.Vector2()) / len(static_ps)
                # 정적 파티클로 회전 추정 (2점 이상 퍼져 있으면 R 결정, 아니면 R=I)
                Axx = Axy = Ayx = Ayy = 0.0
                for p, r in static_ps:
                    s = r - s_rest_c
                    if s.length() < 1e-3: continue
                    q = p.pos - s_cur_c
                    Axx += q.x * s.x; Axy += q.x * s.y
                    Ayx += q.y * s.x; Ayy += q.y * s.y
                denom = Axx + Ayy
                if abs(denom) < 1e-8 and abs(Ayx - Axy) < 1e-8:
                    theta = 0.0
                else:
                    theta = _math.atan2(Ayx - Axy, denom)
                cos_t = _math.cos(theta); sin_t = _math.sin(theta)
                for p, r in rest_list:
                    if p.is_static: continue
                    if id(p) in hinge_pinned: continue
                    rr = r - s_rest_c
                    target = pygame.math.Vector2(
                        s_cur_c.x + cos_t * rr.x - sin_t * rr.y,
                        s_cur_c.y + sin_t * rr.x + cos_t * rr.y)
                    # 정적 프레임에 강체 고정 → 위치 snap + 속도 0 (떠내려감 방지)
                    p.pos = target
                    p.old_pos = target.copy()
                continue

            # A 행렬 계산에 쓸 파티클: 단일 파티클 원(Circle)은 COM과 일치해서
            # atan2(0,0) 수치 불안정 유발 → 다중 파티클 오브젝트 파티클만 사용
            # (단, 전체 파티클이 다 single이면 그냥 다 쓴다)
            # ★ 글루된 스프링 끝점은 '회전 fit'에서 제외한다 → 스프링 당김이
            #   물체를 회전(flop)시키지 않게 함(위치/힘 전달은 그대로). 양끝
            #   weld 용수철이 축 압축/팽창을 유지하면서도 따로 회전하지 않는다.
            _anchors = getattr(self, '_spring_anchors', {})
            multi_rest = [(p, r) for p, r in zip(particles, offsets)
                          if r.length() > 1e-3 and id(p) not in _anchors]
            if not multi_rest:   # 끝점 제외 후 비면 끝점 포함해 재시도
                multi_rest = [(p, r) for p, r in zip(particles, offsets)
                              if r.length() > 1e-3]
            if not multi_rest:
                multi_rest = list(zip(particles, offsets))  # fallback

            if pinned_in_group:
                # ── 힌지 앵커 방식 ───────────────────────────────────────────
                # 힌지 파티클 위치를 앵커로 고정, 나머지만 rigid 배치
                pin_particle = pinned_in_group[0]
                pin_idx = next(i for i, (p, _) in enumerate(rest_list) if p is pin_particle)
                pin_rest_offset = offsets[pin_idx]

                non_pin = [(p, r) for p, r in rest_list
                           if id(p) not in hinge_pinned and not p.is_static]
                if not non_pin:
                    continue

                pin_pos = pin_particle.pos
                n_np = len(non_pin)

                # 앵커 기준 A 행렬 구성 (COM 근접 파티클 제외)
                Axx = Axy = Ayx = Ayy = 0.0
                for p, r in non_pin:
                    s = r - pin_rest_offset
                    if s.length() < 1e-3: continue  # 수치 불안정 방지
                    q = p.pos - pin_pos
                    Axx += q.x * s.x
                    Axy += q.x * s.y
                    Ayx += q.y * s.x
                    Ayy += q.y * s.y

                denom = Axx + Ayy
                if abs(denom) < 1e-8 and abs(Ayx - Axy) < 1e-8:
                    theta = 0.0
                else:
                    theta = _math.atan2(Ayx - Axy, denom)
                cos_t = _math.cos(theta)
                sin_t = _math.sin(theta)

                # COM 역산: com = pin_pos - R * pin_rest_offset
                dcx, dcy = pin_rest_offset.x, pin_rest_offset.y
                com_x = pin_pos.x - (cos_t * dcx - sin_t * dcy)
                com_y = pin_pos.y - (sin_t * dcx + cos_t * dcy)

                for p, r in rest_list:
                    if p.is_static: continue
                    if id(p) in hinge_pinned: continue
                    target_x = com_x + cos_t * r.x - sin_t * r.y
                    target_y = com_y + sin_t * r.x + cos_t * r.y
                    # old_pos는 건드리지 않음 — Verlet 속도 보존
                    # pos만 snap: 다음 프레임 속도 = new_pos - old_pos (회전 포함)
                    delta = pygame.math.Vector2(target_x, target_y) - p.pos
                    p.pos    += delta
                    p.old_pos += delta

            else:
                # ── 힌지 없는 그룹: COM 기반 기존 방식 ─────────────────────
                n = len(particles)
                # 질량 가중 COM (snap 전)
                _tot_m = sum(p.mass for p in particles)
                if _tot_m > 1e-10:
                    cx = sum(p.pos.x * p.mass for p in particles) / _tot_m
                    cy = sum(p.pos.y * p.mass for p in particles) / _tot_m
                else:
                    cx = sum(p.pos.x for p in particles) / n
                    cy = sum(p.pos.y for p in particles) / n
                com = pygame.math.Vector2(cx, cy)

                # A 행렬: COM에서 떨어진 파티클만 사용 (Circle 중심 파티클 제외)
                Axx = Axy = Ayx = Ayy = 0.0
                for p, r in multi_rest:
                    q = p.pos - com
                    Axx += q.x * r.x
                    Axy += q.x * r.y
                    Ayx += q.y * r.x
                    Ayy += q.y * r.y

                denom = Axx + Ayy
                if abs(denom) < 1e-8 and abs(Ayx - Axy) < 1e-8:
                    theta = 0.0  # 수치 불안정 방지
                else:
                    theta = _math.atan2(Ayx - Axy, denom)
                # ── ★ 단일 베이스 파티클(Circle 등) 그룹: 회전 금지(평행이동만).
                #    Circle(파티클 1개)에 스프링 끝점이 글루되면 '2점 강체'가
                #    되어 자유 회전하며 원을 끌고 다닌다(위치 고정 안됨).
                #    스프링 끝점이 아닌 '베이스 파티클'이 2개 미만이면 θ=0. ──
                _anchors = getattr(self, '_spring_anchors', {})
                base_cnt = sum(1 for p in particles if id(p) not in _anchors)
                if base_cnt < 2:
                    theta = 0.0
                cos_t = _math.cos(theta)
                sin_t = _math.sin(theta)

                # snap 후 COM이 이동하지 않도록 보정벡터 계산
                # target_i = com + R * r_i  →  질량 가중 평균 target = com (이론상)
                # 수치 오차로 미세 이동 발생 → 사후 보정
                mob_targets = {}
                for p, r in rest_list:
                    if p.is_static: continue
                    mob_targets[id(p)] = pygame.math.Vector2(
                        com.x + cos_t * r.x - sin_t * r.y,
                        com.y + sin_t * r.x + cos_t * r.y)

                # snap 후 예상 COM
                if _tot_m > 1e-10:
                    snap_cx = sum(
                        (mob_targets[id(p)].x if id(p) in mob_targets else p.pos.x) * p.mass
                        for p in particles) / _tot_m
                    snap_cy = sum(
                        (mob_targets[id(p)].y if id(p) in mob_targets else p.pos.y) * p.mass
                        for p in particles) / _tot_m
                    # COM 오차 보정
                    com_err = pygame.math.Vector2(snap_cx - cx, snap_cy - cy)
                else:
                    com_err = pygame.math.Vector2()

                # ── 위치 snap + 강체 속도 안정화 ──────────────────────────
                # delta를 pos/old_pos 동일 적용해 개별 속도 보존하되,
                # snap 후 그룹 전체 속도를 질량가중 COM 병진속도로 통일하여
                # 바닥 접촉 시 잔류 진동(self-bounce) 제거.
                snapped = []
                for p, r in rest_list:
                    if p.is_static: continue
                    target = mob_targets[id(p)] - com_err  # COM 보존 보정
                    delta  = target - p.pos
                    p.pos     += delta
                    p.old_pos += delta
                    snapped.append(p)

                # 강체 속도 통일: 모든 파티클을 COM 병진속도 + 강체 회전속도로
                # 재설정하면 한 점 충돌이 비대칭 진동으로 남지 않는다.
                if snapped:
                    _m = sum(p.mass for p in snapped)
                    if _m > 1e-10:
                        # COM 병진 속도
                        v_com = sum(((p.pos - p.old_pos) * p.mass for p in snapped),
                                    pygame.math.Vector2()) / _m
                        # 각속도 (관성모멘트로 정규화, clamp로 폭발 방지)
                        com_now = pygame.math.Vector2(
                            sum(p.pos.x * p.mass for p in snapped) / _m,
                            sum(p.pos.y * p.mass for p in snapped) / _m)
                        L = 0.0; I = 0.0
                        for p in snapped:
                            ri = p.pos - com_now
                            vi = (p.pos - p.old_pos) - v_com
                            L += p.mass * (ri.x * vi.y - ri.y * vi.x)
                            I += p.mass * ri.length_squared()
                        omega = L / I if I > 1e-6 else 0.0
                        # 각속도 clamp: 프레임당 과도 회전 방지
                        max_omega = 0.5
                        if omega >  max_omega: omega =  max_omega
                        if omega < -max_omega: omega = -max_omega
                        # 재투영: v_i = v_com + omega × r_i
                        for p in snapped:
                            ri = p.pos - com_now
                            v_rot = pygame.math.Vector2(-omega * ri.y, omega * ri.x)
                            vi = v_com + v_rot
                            p.old_pos = p.pos - vi

    # ── PAUSE 중 제약/충돌 전용 솔버 ──────────────────────────────────────────
    def apply_pending_velocities(self, dt):
        """재생(play) 재개 시 1회 호출.
        pause 중 VELOCITY 모드로 설정해 둔 초기 속도(obj.pending_velocity)를
        Verlet old_pos에 인코딩한다. weld 그룹은 그룹 전체에 동일 속도를 부여.
        """
        if dt <= 0:
            dt = 0.016
        # weld 그룹 단위로 속도 공유 (한 부분만 설정해도 그룹 전체 적용)
        applied_groups = {}
        for obj in self.objects:
            pv = getattr(obj, 'pending_velocity', None)
            if pv is None:
                continue
            wgid = getattr(obj, 'weld_group_id', None)
            if wgid is not None:
                applied_groups[wgid] = pv
        for obj in self.objects:
            pv = getattr(obj, 'pending_velocity', None)
            if pv is None:
                wgid = getattr(obj, 'weld_group_id', None)
                if wgid is not None and wgid in applied_groups:
                    pv = applied_groups[wgid]
            if pv is None:
                continue
            for p in obj.particles:
                if not p.is_static:
                    p.old_pos = p.pos - pv * dt
        # 1회성: 적용 후 제거
        for obj in self.objects:
            if hasattr(obj, 'pending_velocity'):
                del obj.pending_velocity

    def clear_pending_velocities(self):
        """설정한 초기 속도를 취소 (예: pause 중 물체를 드래그로 옮길 때)."""
        for obj in self.objects:
            if hasattr(obj, 'pending_velocity'):
                del obj.pending_velocity

    def paused_solve(self):
        """
        Pause 상태에서 매 프레임 호출.
        Verlet 적분(속도·중력)은 완전히 건너뛰고,
        constraint 길이 구속 + 충돌 위치 보정만 수행.
        → 물체가 제자리에 정지하면서도 attach/weld/충돌은 유지됨.
        """
        # 파티클 캐시 최신화
        for obj in self.objects:
            obj._particle_set = set(id(p) for p in obj.particles)
            for attr in ('weld_group_id', 'z_layer', 'air_drag',
                         'tension_acc', 'spring_acc', 'int_acc',
                         'normal_acc', 'stress_max'):
                if not hasattr(obj, attr):
                    setattr(obj, attr, obj.collision_group if attr == 'weld_group_id' else 0.0)

        all_particles   = []
        all_constraints = list(self.global_constraints)
        for obj in self.objects:
            all_particles.extend(obj.particles)
            all_constraints.extend(obj.constraints)

        # constraint 응력 초기화
        for c in all_constraints:
            c.stress = 0.0

        # constraint solve (충분히 많이 반복해서 완전 수렴)
        iters = min(MAX_CONSTRAINT_ITER, self.constraint_iterations)
        for _ in range(iters):
            # ── 힌지: 매 iteration 완전 위치 일치 (pause 포함) ────────────────
            for c in all_constraints:
                if getattr(c, 'style', '') != 'hinge': continue
                delta = c.p2.pos - c.p1.pos
                dist  = delta.length()
                if dist < 1e-8: continue
                inv_m1 = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                inv_m2 = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                total_w = inv_m1 + inv_m2
                if total_w < 1e-10: continue
                n_hat = delta / dist
                corr  = dist / total_w
                if not c.p1.is_static:
                    c.p1.pos += n_hat * (corr * inv_m1)
                    c.p1.old_pos = c.p1.pos.copy()
                if not c.p2.is_static:
                    c.p2.pos -= n_hat * (corr * inv_m2)
                    c.p2.old_pos = c.p2.pos.copy()

            # ── 일반 Constraint ────────────────────────────────────────────
            for c in all_constraints:
                delta = c.p2.pos - c.p1.pos
                dist  = delta.length()
                if dist == 0: continue

                is_spring = getattr(c, 'style', '') == 'spring'
                if is_spring:
                    # pause 중 스프링: 정지 상태이므로 rest length로 완전 수렴
                    stretch = dist - c.length
                    inv_m1  = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                    inv_m2  = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                    total_w = inv_m1 + inv_m2
                    if total_w < 1e-10: continue
                    n_hat = delta / dist
                    corr  = stretch / total_w * min(c.stiffness, 1.0)
                    if not c.p1.is_static:
                        c.p1.pos += n_hat * (corr * inv_m1)
                        c.p1.old_pos = c.p1.pos.copy()
                    if not c.p2.is_static:
                        c.p2.pos -= n_hat * (corr * inv_m2)
                        c.p2.old_pos = c.p2.pos.copy()
                else:
                    stretch = dist - c.length
                    if not c.is_solid and stretch <= 0: continue
                    inv_m1 = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                    inv_m2 = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                    total_w = inv_m1 + inv_m2
                    if total_w < 1e-10: continue
                    n_hat = delta / dist
                    corr  = stretch / total_w * c.stiffness
                    if not c.p1.is_static:
                        c.p1.pos += n_hat * (corr * inv_m1)
                        c.p1.old_pos = c.p1.pos.copy()
                    if not c.p2.is_static:
                        c.p2.pos -= n_hat * (corr * inv_m2)
                        c.p2.old_pos = c.p2.pos.copy()

            # ── 풀리 Constraint ────────────────────────────────────────────
            for pc in self.pulley_constraints:
                pts     = pc.pts
                num_pts = len(pts)
                if num_pts < 3: continue
                distances, normals, current_len = [], [], 0
                for i in range(num_pts - 1):
                    d = pts[i+1].pos - pts[i].pos
                    dl = d.length()
                    distances.append(dl)
                    current_len += dl
                    normals.append(d / dl if dl > 0 else pygame.math.Vector2(0, 0))
                diff = current_len - pc.length
                if diff <= 0: continue
                grads = []
                for i in range(num_pts):
                    g = pygame.math.Vector2(0, 0)
                    if i > 0:             g += normals[i-1]
                    if i < num_pts - 1:   g -= normals[i]
                    grads.append(g)
                sum_w, inv_masses = 0.0, []
                for i in range(num_pts):
                    inv_m = 0.0 if pts[i].is_static else 1.0 / pts[i].mass
                    inv_masses.append(inv_m)
                    sum_w += inv_m * grads[i].length_squared()
                if sum_w == 0: continue
                corr = (diff / sum_w) * pc.stiffness
                for i in range(num_pts):
                    if not pts[i].is_static:
                        pts[i].pos -= grads[i] * (inv_masses[i] * corr)
                        pts[i].old_pos = pts[i].pos.copy()

            # ── 벽 경계 ────────────────────────────────────────────────────
            for p in all_particles:
                if p.is_static: continue
                if p.pos.y > self.height - p.radius:
                    p.pos.y = self.height - p.radius
                    p.old_pos.y = p.pos.y
                if p.pos.y < p.radius:
                    p.pos.y = p.radius
                    p.old_pos.y = p.pos.y
                if p.pos.x < p.radius:
                    p.pos.x = p.radius
                    p.old_pos.x = p.pos.x
                if p.pos.x > self.width - p.radius:
                    p.pos.x = self.width - p.radius
                    p.old_pos.x = p.pos.x

            # ── 파티클 vs 엣지 충돌 (위치 보정만, 반발 없음) ──────────────
            for p in all_particles:
                if p.is_static: continue
                for c in all_constraints:
                    if not getattr(c, 'is_solid', False): continue
                    # ★ 충돌 OFF된 attach 막대는 모든 물체가 통과 (엣지 충돌 자체 skip)
                    if getattr(c, 'no_collision', False): continue
                    if p.parent and c.parent and not isinstance(c.parent, str) and \
                       hasattr(c.parent, 'collision_group') and \
                       p.parent.collision_group == c.parent.collision_group: continue
                    # weld 그룹 내부 skip
                    if p.parent and c.parent and not isinstance(c.parent, str):
                        wg_p = getattr(p.parent, 'weld_group_id', None)
                        wg_c = getattr(c.parent, 'weld_group_id', None)
                        if wg_p is not None and wg_p == wg_c: continue
                    # attach(global) z_layer 체크: 끝점 부모 기준
                    p_layer = getattr(getattr(p, 'parent', None), 'z_layer', 0)
                    if c.parent == "global":
                        c1_layer = getattr(getattr(c.p1, 'parent', None), 'z_layer', 0)
                        c2_layer = getattr(getattr(c.p2, 'parent', None), 'z_layer', 0)
                        if p_layer != c1_layer or p_layer != c2_layer:
                            continue
                    elif hasattr(c.parent, 'z_layer'):
                        if p_layer != c.parent.z_layer:
                            continue

                    ep1, ep2  = c.p1.pos, c.p2.pos
                    ab        = ep2 - ep1
                    ab_len_sq = ab.length_squared()
                    if ab_len_sq < 1e-8: continue
                    ab_len = ab_len_sq ** 0.5

                    raw_nx = ab.y / ab_len
                    raw_ny = -ab.x / ab_len
                    # ★ 동적 외부 노말: 회전/스케일 후에도 정확 (관통 버그 수정)
                    en = _edge_outward_normal(c)
                    if en:
                        if en[0]*raw_nx + en[1]*raw_ny < 0:
                            raw_nx, raw_ny = -raw_nx, -raw_ny
                        ap   = p.pos - ep1
                        side = ap.x*raw_nx + ap.y*raw_ny
                        if side < -p.radius: continue

                    ap      = p.pos - ep1
                    t_proj  = max(0.0, min(1.0, ap.dot(ab) / ab_len_sq))
                    closest = ep1 + ab * t_proj
                    dist_v  = p.pos - closest
                    dist    = dist_v.length()
                    min_d   = p.radius + 1
                    if dist >= min_d or dist < 1e-6: continue

                    normal = dist_v / dist if dist > 1e-6 else pygame.math.Vector2(raw_nx, raw_ny)
                    if en and normal.dot(pygame.math.Vector2(raw_nx, raw_ny)) < 0: continue

                    overlap = min_d - dist
                    inv_m1  = 1.0 / p.mass
                    inv_m2  = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                    inv_m3  = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                    tot_w   = inv_m1 + (1-t_proj)*inv_m2 + t_proj*inv_m3
                    if tot_w < 1e-10: continue

                    push_p = overlap * inv_m1 / tot_w
                    push_e = overlap * ((1-t_proj)*inv_m2 + t_proj*inv_m3) / tot_w

                    p.pos += normal * push_p
                    p.old_pos = p.pos.copy()
                    if not c.p1.is_static:
                        c.p1.pos -= normal * push_e * (1-t_proj)
                        c.p1.old_pos = c.p1.pos.copy()
                    if not c.p2.is_static:
                        c.p2.pos -= normal * push_e * t_proj
                        c.p2.old_pos = c.p2.pos.copy()

            # ── 파티클 vs 파티클 충돌 (위치 보정만) ──────────────────────
            _nc_set_ps = self._build_no_collision_set()
            n = len(all_particles)
            for i in range(n):
                for j in range(i + 1, n):
                    p1, p2 = all_particles[i], all_particles[j]
                    if _same_group(p1, p2): continue
                    if _different_layer(p1, p2): continue
                    if _nc_set_ps:
                        objA = getattr(p1, 'parent', None)
                        objB = getattr(p2, 'parent', None)
                        if objA and objB and frozenset((id(objA), id(objB))) in _nc_set_ps:
                            continue

                    delta    = p1.pos - p2.pos
                    dist     = delta.length()
                    min_dist = p1.radius + p2.radius
                    if dist >= min_dist: continue
                    if dist < 1e-6: delta, dist = pygame.math.Vector2(1, 0), 1.0

                    overlap = min_dist - dist
                    normal  = delta / dist
                    inv_m1  = 0.0 if p1.is_static else 1.0 / p1.mass
                    inv_m2  = 0.0 if p2.is_static else 1.0 / p2.mass
                    total_w = inv_m1 + inv_m2
                    if total_w < 1e-10: continue

                    if not p1.is_static:
                        p1.pos += normal * (overlap * inv_m1 / total_w)
                        p1.old_pos = p1.pos.copy()
                    if not p2.is_static:
                        p2.pos -= normal * (overlap * inv_m2 / total_w)
                        p2.old_pos = p2.pos.copy()

            # ── SAT 폴리곤 충돌 (pause 중) ────────────────────────────────
            n_obj = len(self.objects)
            for oi in range(n_obj):
                for oj in range(oi + 1, n_obj):
                    objA, objB = self.objects[oi], self.objects[oj]
                    if objA.collision_group == objB.collision_group: continue
                    wgA = getattr(objA, 'weld_group_id', None)
                    wgB = getattr(objB, 'weld_group_id', None)
                    if wgA is not None and wgA == wgB: continue
                    if getattr(objA, 'z_layer', 0) != getattr(objB, 'z_layer', 0): continue
                    nA = getattr(objA, 'name', '')
                    nB = getattr(objB, 'name', '')
                    if nA in ('Spring', 'String'): continue
                    if nB in ('Spring', 'String'): continue

                    # ★ 오목 도형 대응: 볼록 조각 단위 SAT (collision.py)
                    hit, normal, depth = sat_collide_objects(objA, objB)
                    if not hit or depth < 1e-4: continue

                    all_static_A = all(p.is_static for p in objA.particles)
                    all_static_B = all(p.is_static for p in objB.particles)
                    if all_static_A and all_static_B: continue

                    mA = objA.mass if objA.mass > 0 else 1.0
                    mB = objB.mass if objB.mass > 0 else 1.0
                    inv_mA = 0.0 if all_static_A else 1.0 / mA
                    inv_mB = 0.0 if all_static_B else 1.0 / mB
                    tot_w  = inv_mA + inv_mB
                    if tot_w < 1e-10: continue

                    pushA = depth * inv_mA / tot_w
                    pushB = depth * inv_mB / tot_w

                    for p in objA.particles:
                        if not p.is_static:
                            p.pos -= normal * pushA
                            p.old_pos = p.pos.copy()
                    for p in objB.particles:
                        if not p.is_static:
                            p.pos += normal * pushB
                            p.old_pos = p.pos.copy()

        # ── Shape Matching: weld 그룹 강체 복원 (pause 중) ──────────────────
        self._apply_shape_matching()
        self._apply_spring_weld_orientation()  # 용수철 회전 구속
        self._apply_spring_both_ends_axis()    # 양끝 weld 용수철 회전 구속

        # ── ImageBlock 자체 강체 복원 (pause 중) ───────────────────────────
        for obj in self.objects:
            if getattr(obj, 'name', '') == 'ImageBlock' and hasattr(obj, 'apply_rigid_match'):
                wgid = getattr(obj, 'weld_group_id', None)
                if wgid in getattr(self, "_weld_rest", {}):
                    continue
                obj.apply_rigid_match()

        # ── 힌지 재보정 (pause 중, 강한 구속) ──────────────────────────────
        for _hp in range(8):
            moved = False
            for c in self.global_constraints:
                if getattr(c, 'style', '') != 'hinge': continue
                delta = c.p2.pos - c.p1.pos
                dist  = delta.length()
                if dist < 1e-7: continue
                inv_m1 = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                inv_m2 = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                total_w = inv_m1 + inv_m2
                if total_w < 1e-10: continue
                n_hat = delta / dist
                corr  = dist / total_w
                if not c.p1.is_static:
                    c.p1.pos += n_hat * (corr * inv_m1)
                    c.p1.old_pos = c.p1.pos.copy()
                if not c.p2.is_static:
                    c.p2.pos -= n_hat * (corr * inv_m2)
                    c.p2.old_pos = c.p2.pos.copy()
                moved = True
            if not moved: break

    # ── 메인 업데이트 ──────────────────────────────────────────────────────────
    def update(self, dt):
        if dt <= 0: return

        subs = max(1, self._current_substeps)

        # constraint 반복 횟수: substep 증가에 비례 (수렴 품질 보장)
        # substep=1 → 20회, substep=10 → 30회, substep=100 → 60회 (대수 스케일)
        import math as _math
        self.constraint_iterations = min(
            MAX_CONSTRAINT_ITER,
            int(BASE_CONSTRAINT_ITER + 12 * _math.log2(max(1, subs)))
        )

        # 파티클 집합 캐시 갱신
        for obj in self.objects:
            obj._particle_set = set(id(p) for p in obj.particles)
            if not hasattr(obj, 'tension_acc'):    obj.tension_acc    = 0.0
            if not hasattr(obj, 'spring_acc'):     obj.spring_acc     = 0.0
            if not hasattr(obj, 'int_acc'):        obj.int_acc        = 0.0
            if not hasattr(obj, 'normal_acc'):     obj.normal_acc     = 0.0  # ★ 수직항력 누산
            if not hasattr(obj, 'stress_max'):     obj.stress_max     = 0.0  # ★ 최대 응력
            if not hasattr(obj, 'weld_group_id'):  obj.weld_group_id  = obj.collision_group
            if not hasattr(obj, 'z_layer'):        obj.z_layer        = 0
            if not hasattr(obj, 'air_drag'):       obj.air_drag       = 0.0

        # ① dt 스케일 보정 (프레임 드랍 시 속도 연속성 유지)
        if self.last_dt > 0.0 and dt != self.last_dt:
            scale_factor = dt / self.last_dt
            for obj in self.objects:
                for p in obj.particles:
                    if not p.is_static:
                        vel = p.pos - p.old_pos
                        p.old_pos = p.pos - vel * scale_factor
        self.last_dt = dt

        # ② Deep-Overlap 빠른 분리
        for i in range(len(self.objects)):
            for j in range(i + 1, len(self.objects)):
                obj1, obj2 = self.objects[i], self.objects[j]
                if obj1.collision_group == obj2.collision_group: continue
                wg1 = getattr(obj1, 'weld_group_id', None)
                wg2 = getattr(obj2, 'weld_group_id', None)
                if wg1 is not None and wg1 == wg2: continue
                if getattr(obj1, 'z_layer', 0) != getattr(obj2, 'z_layer', 0): continue
                if getattr(obj1, 'name', '') in ['Spring', 'String'] or \
                   getattr(obj2, 'name', '') in ['Spring', 'String']: continue
                if not obj1.particles or not obj2.particles: continue

                c1 = sum((p.pos for p in obj1.particles), pygame.math.Vector2()) / len(obj1.particles)
                c2 = sum((p.pos for p in obj2.particles), pygame.math.Vector2()) / len(obj2.particles)
                dist = c1.distance_to(c2)
                r1 = max(p.pos.distance_to(c1) for p in obj1.particles)
                r2 = max(p.pos.distance_to(c2) for p in obj2.particles)
                min_dist = r1 + r2

                if dist < min_dist * 0.35:
                    dir_vec = pygame.math.Vector2(1, 0) if dist == 0 else (c1 - c2) / dist
                    push_amount = (min_dist * 0.35 - dist) * 0.05
                    m1 = obj1.mass if obj1.mass > 0 else 1.0
                    m2 = obj2.mass if obj2.mass > 0 else 1.0
                    inv_m1, inv_m2 = 1.0 / m1, 1.0 / m2
                    tot_w = inv_m1 + inv_m2
                    if tot_w > 0:
                        for p in obj1.particles:
                            if not p.is_static: p.pos += dir_vec * push_amount * (inv_m1 / tot_w)
                        for p in obj2.particles:
                            if not p.is_static: p.pos -= dir_vec * push_amount * (inv_m2 / tot_w)

        # ③ Verlet 적분 + 공기저항
        all_particles   = []
        all_constraints = list(self.global_constraints)
        _nc_set = self._build_no_collision_set()  # no_collision 억제 쌍 (전 충돌 루프 공유)
        # weld 그룹에 속한 파티클 id (개별 반발 억제용)
        self._weld_member_ids = set()
        if hasattr(self, '_weld_rest') and self._weld_rest:
            for rest_list in self._weld_rest.values():
                for p, _ in rest_list:
                    self._weld_member_ids.add(id(p))

        for obj in self.objects:
            all_particles.extend(obj.particles)
            all_constraints.extend(obj.constraints)

            is_circle = isinstance(obj, Circle)

            for p in obj.particles:
                if p.is_static: continue

                velocity = p.pos - p.old_pos
                speed_sq = velocity.length_squared()

                # A. 공기저항 (implicit 감쇠)
                if speed_sq > 1e-8:
                    speed = speed_sq ** 0.5
                    obj_air   = getattr(p.parent, 'air_drag', 0.0) if p.parent else 0.0
                    total_air = self.air_drag_coeff + obj_air * 0.01
                    air_damp  = 1.0 / (1.0 + total_air * speed * dt)
                    velocity *= air_damp

                # B. 구름 마찰 (원형 한정)
                if is_circle:
                    roll_damp = 1.0 - self.rolling_drag_coeff * dt * 60.0
                    if roll_damp > 0: velocity *= roll_damp

                p.old_pos  = p.pos.copy()
                g_vec = self.gravity if self.gravity_enabled else pygame.math.Vector2(0, 0)
                p.pos += velocity + g_vec * (dt * dt)

        # 탄성 반발 pre-pass (Verlet 직후)
        self._apply_restitution_inline(all_particles, dt)

        # ④ 제약 풀기 (XPBD/PBD)
        # constraint 풀기 전 파티클 위치 스냅샷 (응력 계산용)
        pre_pos = {id(p): p.pos.copy() for p in all_particles}

        # ── constraint별 응력 누산기 초기화 ────────────────────────────────
        # c.stress: 이번 프레임에 이 constraint가 받은 응력 크기 (N)
        for c in all_constraints:
            c.stress = 0.0

        for iteration in range(self.constraint_iterations):
            # ── 힌지 Constraint: 매 iteration마다 완전 위치 일치 ─────────────
            # 일반 constraint 루프보다 먼저 실행해 최우선 수렴 보장
            for c in all_constraints:
                if getattr(c, 'style', '') != 'hinge': continue
                delta = c.p2.pos - c.p1.pos
                dist  = delta.length()
                if dist < 1e-8: continue
                inv_m1 = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                inv_m2 = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                total_w = inv_m1 + inv_m2
                if total_w < 1e-10: continue
                # 거리를 0으로: 두 파티클을 완전히 같은 위치로 당김 (stiffness=1 완전 보정)
                n_hat = delta / dist
                corr  = dist / total_w  # c.length == 0 이므로 stretch == dist
                if not c.p1.is_static: c.p1.pos += n_hat * (corr * inv_m1)
                if not c.p2.is_static: c.p2.pos -= n_hat * (corr * inv_m2)

            # ── 일반 Constraint (XPBD) ────────────────────────────────────
            for c in all_constraints:
                delta = c.p2.pos - c.p1.pos
                dist  = delta.length()
                if dist == 0: continue

                is_spring = getattr(c, 'style', '') == 'spring'

                if is_spring:
                    # ── 스프링 (XPBD 탄성): compliance α 적용 ─────────────
                    alpha   = self.xpbd_spring_alpha(c.stiffness, dt)
                    stretch = dist - c.length
                    inv_m1  = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                    inv_m2  = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                    total_w = inv_m1 + inv_m2 + alpha
                    if total_w < 1e-10: continue
                    # XPBD 위치 보정
                    d_lambda = -stretch / total_w
                    n_hat    = delta / dist
                    if not c.p1.is_static:
                        c.p1.pos -= n_hat * (d_lambda * inv_m1)
                    if not c.p2.is_static:
                        c.p2.pos += n_hat * (d_lambda * inv_m2)
                    # 응력 누산: F = k * stretch
                    f_spring = abs(stretch) * c.stiffness * 1e6
                    c.stress += f_spring / max(self.constraint_iterations, 1)

                else:
                    # ── 실/구조 Constraint: 완전 길이 구속 ────────────────
                    stretch = dist - c.length
                    if not c.is_solid and stretch <= 0:
                        # is_solid=False: 압축은 허용 (실 방향)
                        continue
                    inv_m1 = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                    inv_m2 = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                    total_w = inv_m1 + inv_m2
                    if total_w < 1e-10: continue
                    n_hat = delta / dist
                    corr  = stretch / total_w * c.stiffness
                    if not c.p1.is_static: c.p1.pos += n_hat * (corr * inv_m1)
                    if not c.p2.is_static: c.p2.pos -= n_hat * (corr * inv_m2)
                    # 응력 누산: F = m * |Δpos| / dt²
                    if not c.p1.is_static:
                        f1 = c.p1.mass * abs(corr * inv_m1) / max(dt * dt, 1e-10)
                        c.stress += f1 / max(self.constraint_iterations, 1)

            # ── 풀리 Constraint ────────────────────────────────────────────
            for pc in self.pulley_constraints:
                pts     = pc.pts
                num_pts = len(pts)
                if num_pts < 3: continue

                distances, normals, current_len = [], [], 0
                for i in range(num_pts - 1):
                    delta   = pts[i+1].pos - pts[i].pos
                    dist    = delta.length()
                    distances.append(dist)
                    current_len += dist
                    normals.append(delta / dist if dist > 0 else pygame.math.Vector2(0, 0))

                diff = current_len - pc.length
                if diff <= 0: continue

                grads = []
                for i in range(num_pts):
                    g = pygame.math.Vector2(0, 0)
                    if i > 0:             g += normals[i-1]
                    if i < num_pts - 1:   g -= normals[i]
                    grads.append(g)

                sum_w, inv_masses = 0, []
                for i in range(num_pts):
                    inv_m = 0.0 if pts[i].is_static else 1.0 / pts[i].mass
                    inv_masses.append(inv_m)
                    sum_w += inv_m * grads[i].length_squared()

                if sum_w == 0: continue
                corr = (diff / sum_w) * pc.stiffness
                for i in range(num_pts):
                    if not pts[i].is_static:
                        pts[i].pos -= grads[i] * (inv_masses[i] * corr)

            # ── 벽 경계 (탄성 반발 + 수직항력 누산) ─────────────────────────
            for p in all_particles:
                if p.is_static: continue
                e   = getattr(getattr(p, 'parent', None), 'restitution', 0.5)
                # weld 그룹 파티클은 벽 반발 억제 (그룹 전체 과반발/튐 방지)
                if id(p) in self._weld_member_ids:
                    e = 0.0
                vel = p.pos - p.old_pos

                mu_p = getattr(getattr(p, 'parent', None), 'friction', 0.01)

                # ── 바닥 ─────────────────────────────────────────────────
                if p.pos.y > self.height - p.radius:
                    pen = p.pos.y - (self.height - p.radius)
                    p.pos.y = self.height - p.radius
                    p.normal_offset.y -= pen
                    if vel.y > 0:
                        # 반발: 법선 속도 반전
                        p.old_pos.y = p.pos.y + vel.y * e
                        # 수직항력 = 접촉 법선 방향 충격량 / dt
                        normal_imp = p.mass * abs(vel.y) * (1.0 + e) / max(dt, 1e-6)
                        self._accum_normal_impulse(p, pygame.math.Vector2(0, -1), normal_imp)
                        # 바닥 쿨롱 마찰 (tangent = x 방향)
                        if mu_p > 0:
                            vt = vel.x
                            fric_imp = mu_p * normal_imp * dt / max(p.mass, 1e-6)
                            dvt = -vt * min(1.0, fric_imp / max(abs(vt), 1e-8))
                            p.old_pos.x -= dvt

                # ── 천장 ─────────────────────────────────────────────────
                if p.pos.y < p.radius:
                    pen = p.radius - p.pos.y
                    p.pos.y = p.radius
                    p.normal_offset.y += pen
                    if vel.y < 0:
                        p.old_pos.y = p.pos.y + vel.y * e
                        normal_imp = p.mass * abs(vel.y) * (1.0 + e) / max(dt, 1e-6)
                        self._accum_normal_impulse(p, pygame.math.Vector2(0, 1), normal_imp)
                        if mu_p > 0:
                            vt = vel.x
                            fric_imp = mu_p * normal_imp * dt / max(p.mass, 1e-6)
                            dvt = -vt * min(1.0, fric_imp / max(abs(vt), 1e-8))
                            p.old_pos.x -= dvt

                # ── 왼쪽 벽 ──────────────────────────────────────────────
                if p.pos.x < p.radius:
                    pen = p.radius - p.pos.x
                    p.pos.x = p.radius
                    p.normal_offset.x += pen
                    if vel.x < 0:
                        p.old_pos.x = p.pos.x + vel.x * e
                        normal_imp = p.mass * abs(vel.x) * (1.0 + e) / max(dt, 1e-6)
                        self._accum_normal_impulse(p, pygame.math.Vector2(1, 0), normal_imp)
                        if mu_p > 0:
                            vt = vel.y
                            fric_imp = mu_p * normal_imp * dt / max(p.mass, 1e-6)
                            dvt = -vt * min(1.0, fric_imp / max(abs(vt), 1e-8))
                            p.old_pos.y -= dvt

                # ── 오른쪽 벽 ─────────────────────────────────────────────
                if p.pos.x > self.width - p.radius:
                    pen = p.pos.x - (self.width - p.radius)
                    p.pos.x = self.width - p.radius
                    p.normal_offset.x -= pen
                    if vel.x > 0:
                        p.old_pos.x = p.pos.x + vel.x * e
                        normal_imp = p.mass * abs(vel.x) * (1.0 + e) / max(dt, 1e-6)
                        self._accum_normal_impulse(p, pygame.math.Vector2(-1, 0), normal_imp)
                        if mu_p > 0:
                            vt = vel.y
                            fric_imp = mu_p * normal_imp * dt / max(p.mass, 1e-6)
                            dvt = -vt * min(1.0, fric_imp / max(abs(vt), 1e-8))
                            p.old_pos.y -= dvt

            # ── 파티클 vs 엣지 충돌 (CCD + 위치 보정 + 정확한 수직항력) ────
            for p in all_particles:
                if p.is_static: continue
                for c in all_constraints:
                    if not getattr(c, 'is_solid', False): continue
                    # ★ 충돌 OFF된 attach 막대는 모든 물체가 통과 (엣지 충돌 자체 skip)
                    if getattr(c, 'no_collision', False): continue
                    if p.parent and c.parent and not isinstance(c.parent, str) and \
                       hasattr(c.parent, 'collision_group') and \
                       p.parent.collision_group == c.parent.collision_group: continue
                    # weld 그룹 내부 파티클-엣지 충돌 skip
                    if p.parent and c.parent and not isinstance(c.parent, str):
                        wg_p = getattr(p.parent, 'weld_group_id', None)
                        wg_c = getattr(c.parent, 'weld_group_id', None)
                        if wg_p is not None and wg_p == wg_c: continue
                    # no_collision 억제 쌍 검사 (파티클 vs 엣지 양 끝점의 부모)
                    if _nc_set:
                        _po = getattr(p, 'parent', None)
                        if _po and any(
                            frozenset((id(_po), id(_eo))) in _nc_set
                            for _eo in (getattr(c.p1, 'parent', None),
                                        getattr(c.p2, 'parent', None))
                            if _eo and _eo is not _po
                        ): continue

                    # ── z_layer 체크 ───────────────────────────────────────
                    # attach(c.parent=="global")는 엣지 끝점 파티클의 부모 z_layer로 판단
                    p_layer = getattr(getattr(p, 'parent', None), 'z_layer', 0)
                    if c.parent == "global":
                        # attach 엣지: 양 끝점 부모 중 하나라도 p와 다른 layer면 skip
                        c1_layer = getattr(getattr(c.p1, 'parent', None), 'z_layer', 0)
                        c2_layer = getattr(getattr(c.p2, 'parent', None), 'z_layer', 0)
                        if p_layer != c1_layer or p_layer != c2_layer:
                            continue
                    elif hasattr(c.parent, 'z_layer'):
                        if p_layer != c.parent.z_layer:
                            continue
                    is_spring_col = (getattr(p.parent, 'name', '') == 'Spring' or
                                     (c.parent and getattr(c.parent, 'name', '') == 'Spring'))
                    if not self.enable_spring_collision and is_spring_col: continue
                    is_attach_col = (c.parent == "global" and c.is_solid
                                     and getattr(c, 'style', 'line') not in ('weld', 'hinge'))
                    if not self.enable_attach_collision and is_attach_col: continue

                    ep1, ep2  = c.p1.pos, c.p2.pos
                    ab        = ep2 - ep1
                    ab_len_sq = ab.length_squared()
                    if ab_len_sq < 1e-8: continue
                    ab_len = ab_len_sq ** 0.5

                    raw_nx = ab.y / ab_len
                    raw_ny = -ab.x / ab_len

                    # ★ 동적 외부 노말: 회전/스케일 후에도 정확 (관통 버그 수정)
                    en = _edge_outward_normal(c)
                    if en:
                        if en[0]*raw_nx + en[1]*raw_ny < 0:
                            raw_nx, raw_ny = -raw_nx, -raw_ny
                        ap   = p.pos - ep1
                        side = ap.x*raw_nx + ap.y*raw_ny
                        if side < -p.radius: continue

                    old_pos = p.old_pos
                    nx_v    = pygame.math.Vector2(raw_nx, raw_ny)
                    ep1_off = ep1 + nx_v * p.radius
                    ep2_off = ep2 + nx_v * p.radius
                    crossed, t_cross = _segment_intersect(old_pos, p.pos, ep1_off, ep2_off)
                    if crossed:
                        cross_pt = old_pos + (p.pos - old_pos) * t_cross
                        p.pos = cross_pt
                        vel   = p.pos - p.old_pos
                        vel_n = vel.dot(nx_v)
                        if vel_n < 0:
                            p.old_pos = p.pos - (vel - nx_v * vel_n)
                            # CCD 수직항력 누산
                            normal_imp = p.mass * abs(vel_n) / max(dt, 1e-6)
                            self._accum_normal_impulse(p, nx_v, normal_imp)
                        p.normal_offset += nx_v * p.radius
                        continue

                    # ── 정적 위치 보정 ─────────────────────────────────────
                    ap      = p.pos - ep1
                    t_proj  = max(0.0, min(1.0, ap.dot(ab) / ab_len_sq))
                    closest = ep1 + ab * t_proj
                    dist_vec= p.pos - closest
                    dist    = dist_vec.length()
                    min_d   = p.radius + 1

                    if dist >= min_d or dist < 1e-6: continue

                    normal = dist_vec / dist if dist > 1e-6 else nx_v
                    if en and normal.dot(pygame.math.Vector2(raw_nx, raw_ny)) < 0:
                        continue

                    overlap = min_d - dist
                    inv_m1  = 1.0 / p.mass
                    inv_m2  = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                    inv_m3  = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                    tot_w   = inv_m1 + (1-t_proj)*inv_m2 + t_proj*inv_m3
                    if tot_w < 1e-10: continue

                    push_p  = overlap * inv_m1 / tot_w
                    push_e  = overlap * ((1-t_proj)*inv_m2 + t_proj*inv_m3) / tot_w

                    p.pos += normal * push_p
                    p.normal_offset += normal * push_p
                    if not c.p1.is_static:
                        c.p1.pos -= normal * push_e * (1-t_proj)
                        c.p1.normal_offset -= normal * push_e * (1-t_proj)
                    if not c.p2.is_static:
                        c.p2.pos -= normal * push_e * t_proj
                        c.p2.normal_offset -= normal * push_e * t_proj

                    # ── 탄성 반발 (엣지-파티클) ────────────────────────────
                    ep   = getattr(getattr(p, 'parent', None), 'restitution', 0.5)
                    ee1  = getattr(getattr(c.p1, 'parent', None), 'restitution', 0.5)
                    ee2  = getattr(getattr(c.p2, 'parent', None), 'restitution', 0.5)
                    e    = (ep * (ee1 + ee2) * 0.5) ** 0.5
                    # weld 그룹 파티클은 개별 반발 억제 (그룹 전체 과반발 방지)
                    # 반발은 shape matching의 각운동량 재투영이 강체로 처리
                    if id(p) in self._weld_member_ids:
                        e *= 0.0

                    vel_p  = p.pos - p.old_pos
                    rel_vn = vel_p.dot(normal)
                    if rel_vn < 0:
                        j_imp = (1.0 + e) * rel_vn / max(tot_w, 1e-9)
                        if not p.is_static:
                            p.old_pos += normal * ((1.0 + e) * rel_vn * inv_m1 / max(tot_w, 1e-9))
                        # ★ 수직항력 누산: 접촉 충격량 기반
                        normal_imp_p = abs(rel_vn) * inv_m1 / max(tot_w, 1e-9) * p.mass / max(dt, 1e-6)
                        self._accum_normal_impulse(p, normal, normal_imp_p)

                        if not c.p1.is_static:
                            c.p1.old_pos -= normal * (j_imp * inv_m2 * (1-t_proj))
                        if not c.p2.is_static:
                            c.p2.old_pos -= normal * (j_imp * inv_m3 * t_proj)

                    # ── 쿨롱 마찰 (엣지 접촉) ─────────────────────────────
                    mu_p_val  = getattr(p.parent, 'friction', 0.01) if p.parent else 0.01
                    mu_c_par  = c.parent if (c.parent and c.parent != "global") else None
                    mu_c_val  = getattr(mu_c_par, 'friction', 0.01) if mu_c_par else 0.01
                    mu_k      = (mu_p_val * mu_c_val) ** 0.5

                    if mu_k > 0:
                        tangent      = pygame.math.Vector2(-normal.y, normal.x)
                        vel_tang     = (p.pos - p.old_pos).dot(tangent)
                        # 정확한 쿨롱 마찰: 마찰력 ≤ μ × 수직항력
                        normal_force = overlap / max(tot_w, 1e-8)
                        fric_max     = mu_k * normal_force
                        # 접선 방향 속도 변화량
                        delta_vt = -vel_tang * min(1.0, fric_max / max(abs(vel_tang), 1e-8))
                        if not p.is_static:
                            p.old_pos -= tangent * (delta_vt * inv_m1 / tot_w)
                        # 엣지 양 끝 파티클에도 반력
                        if not c.p1.is_static:
                            c.p1.old_pos += tangent * (delta_vt * inv_m2 * (1-t_proj) / tot_w)
                        if not c.p2.is_static:
                            c.p2.old_pos += tangent * (delta_vt * inv_m3 * t_proj / tot_w)

            # ── 파티클 vs 파티클 충돌 (위치 보정 + 마찰 + 수직항력) ─────────
            n = len(all_particles)
            for i in range(n):
                for j in range(i + 1, n):
                    p1, p2 = all_particles[i], all_particles[j]
                    if _same_group(p1, p2): continue
                    if _different_layer(p1, p2): continue
                    # no_collision 억제 쌍 검사 (Circle 포함 모든 파티클)
                    if _nc_set:
                        objA = getattr(p1, 'parent', None)
                        objB = getattr(p2, 'parent', None)
                        if objA and objB and frozenset((id(objA), id(objB))) in _nc_set:
                            continue

                    delta    = p1.pos - p2.pos
                    dist     = delta.length()
                    min_dist = p1.radius + p2.radius
                    if dist >= min_dist: continue

                    if dist < 1e-6: delta, dist = pygame.math.Vector2(1, 0), 1.0
                    overlap  = min_dist - dist
                    normal   = delta / dist
                    inv_m1   = 0.0 if p1.is_static else 1.0 / p1.mass
                    inv_m2   = 0.0 if p2.is_static else 1.0 / p2.mass
                    total_w  = inv_m1 + inv_m2
                    if total_w < 1e-10: continue

                    # 위치 보정 (겹침 해소)
                    correction = normal * overlap
                    if not p1.is_static:
                        corr1 = correction * (inv_m1 / total_w)
                        p1.pos           += corr1
                        p1.normal_offset += corr1
                    if not p2.is_static:
                        corr2 = correction * (inv_m2 / total_w)
                        p2.pos           -= corr2
                        p2.normal_offset -= corr2

                    # ★ 수직항력 누산 (파티클-파티클 접촉)
                    normal_imp_pp = overlap / max(total_w, 1e-8) * 0.5 / max(dt * dt, 1e-10)
                    if not p1.is_static:
                        self._accum_normal_impulse(p1, normal, normal_imp_pp * p1.mass)
                    if not p2.is_static:
                        self._accum_normal_impulse(p2, -normal, normal_imp_pp * p2.mass)

                    # 쿨롱 마찰 (파티클-파티클)
                    mu_1  = getattr(p1.parent, 'friction', 0.01) if p1.parent else 0.01
                    mu_2  = getattr(p2.parent, 'friction', 0.01) if p2.parent else 0.01
                    mu_k  = (mu_1 * mu_2) ** 0.5

                    if mu_k > 0:
                        tangent          = pygame.math.Vector2(-normal.y, normal.x)
                        vel_p1           = p1.pos - p1.old_pos
                        vel_p2           = p2.pos - p2.old_pos
                        rel_v_t          = (vel_p1 - vel_p2).dot(tangent)
                        normal_impulse   = overlap / max(total_w, 1e-8)
                        friction_impulse = mu_k * normal_impulse
                        delta_v_t = -rel_v_t * min(1.0, friction_impulse / max(abs(rel_v_t), 1e-8))
                        if not p1.is_static:
                            p1.old_pos -= tangent * (delta_v_t * inv_m1 / total_w)
                        if not p2.is_static:
                            p2.old_pos += tangent * (delta_v_t * inv_m2 / total_w)

            # ── SAT 폴리곤 충돌 (박스/삼각형 등 면-면 겹침 해소) ─────────────
            # 파티클 레벨 보정만으로는 놓치는 면-면 겹침을 SAT로 잡아낸다.
            n_obj = len(self.objects)
            for oi in range(n_obj):
                for oj in range(oi + 1, n_obj):
                    objA, objB = self.objects[oi], self.objects[oj]
                    if objA.collision_group == objB.collision_group: continue
                    if getattr(objA, 'z_layer', 0) != getattr(objB, 'z_layer', 0): continue
                    # no_collision 억제 쌍 검사
                    if frozenset((id(objA), id(objB))) in _nc_set: continue
                    # Spring/String/ImageBlock은 SAT 제외
                    nA = getattr(objA, 'name', '')
                    nB = getattr(objB, 'name', '')
                    if nA in ('Spring', 'String'): continue
                    if nB in ('Spring', 'String'): continue

                    # 원은 파티클vs파티클로 이미 처리됨 — 폴리곤끼리만
                    # ★ 오목 도형 대응: 볼록 조각 단위 SAT (collision.py)
                    hit, normal, depth = sat_collide_objects(objA, objB)
                    if not hit or depth < 1e-4: continue

                    # 질량 비례 보정
                    mA = objA.mass if objA.mass > 0 else 1.0
                    mB = objB.mass if objB.mass > 0 else 1.0
                    all_static_A = all(p.is_static for p in objA.particles)
                    all_static_B = all(p.is_static for p in objB.particles)
                    if all_static_A and all_static_B: continue

                    inv_mA = 0.0 if all_static_A else 1.0 / mA
                    inv_mB = 0.0 if all_static_B else 1.0 / mB
                    tot_w  = inv_mA + inv_mB
                    if tot_w < 1e-10: continue

                    pushA = depth * inv_mA / tot_w
                    pushB = depth * inv_mB / tot_w

                    # 모든 파티클을 오브젝트 중심으로 이동 (rigid body처럼)
                    for p in objA.particles:
                        if not p.is_static:
                            p.pos -= normal * pushA
                    for p in objB.particles:
                        if not p.is_static:
                            p.pos += normal * pushB

                    # ★ 침투 방향 잔류 속도 제거: SAT로 분리한 직후,
                    #   법선 방향으로 여전히 파고드는 속도를 각 파티클에서 죽인다.
                    #   (좁은 틈에서 둘레 파티클이 모서리를 타고 미끄러져 빠지는
                    #    터널링을 막는다. 면 전체에 일관 적용되어 강체처럼 멈춤.)
                    if not all_static_A:
                        for p in objA.particles:
                            if p.is_static: continue
                            v = p.pos - p.old_pos
                            vn = v.dot(normal)
                            if vn > 0:   # objA는 -normal로 분리 → +normal 속도가 침투
                                p.old_pos = p.old_pos + normal * vn
                    if not all_static_B:
                        for p in objB.particles:
                            if p.is_static: continue
                            v = p.pos - p.old_pos
                            vn = v.dot(normal)
                            if vn < 0:   # objB는 +normal로 분리 → -normal 속도가 침투
                                p.old_pos = p.old_pos + normal * vn

                    # 반발 속도 처리 (오브젝트 무게중심 속도 기반)
                    cA_parts = [p for p in objA.particles if not p.is_static]
                    cB_parts = [p for p in objB.particles if not p.is_static]
                    if not cA_parts or not cB_parts: continue

                    velA = sum((p.pos - p.old_pos for p in cA_parts), pygame.math.Vector2()) / len(cA_parts)
                    velB = sum((p.pos - p.old_pos for p in cB_parts), pygame.math.Vector2()) / len(cB_parts)
                    rel_vn = (velA - velB).dot(normal)

                    # ★ 반발 충격량은 마지막 iteration에서 1회만 적용.
                    #   매 iteration 적용하면 같은 충돌의 반발이 누적돼
                    #   ImageBlock이 바닥에서 과도하게 튀어오르고, 그 반동으로
                    #   다음 프레임에 바닥을 뚫는 문제가 있었다.
                    if rel_vn < 0 and iteration == self.constraint_iterations - 1:
                        eA = getattr(objA, 'restitution', 0.5)
                        eB = getattr(objB, 'restitution', 0.5)
                        e  = (eA * eB) ** 0.5
                        j  = -(1.0 + e) * rel_vn / tot_w

                        for p in cA_parts:
                            p.old_pos -= normal * (j * inv_mA)
                        for p in cB_parts:
                            p.old_pos += normal * (j * inv_mB)

                        # 쿨롱 마찰
                        mu_A = getattr(objA, 'friction', 0.01)
                        mu_B = getattr(objB, 'friction', 0.01)
                        mu_k = (mu_A * mu_B) ** 0.5
                        if mu_k > 0:
                            tangent = pygame.math.Vector2(-normal.y, normal.x)
                            rel_vt  = (velA - velB).dot(tangent)
                            fric_imp = mu_k * abs(j)
                            dv_t = -rel_vt * min(1.0, fric_imp / max(abs(rel_vt), 1e-8))
                            for p in cA_parts:
                                p.old_pos -= tangent * (dv_t * inv_mA / tot_w)
                            for p in cB_parts:
                                p.old_pos += tangent * (dv_t * inv_mB / tot_w)

        # ── Shape Matching: weld 그룹 강체 복원 ────────────────────────────
        # 모든 constraint/충돌 보정이 끝난 뒤 weld 그룹을 rigid body로 고정
        self._apply_shape_matching()
        # ── 용수철 회전 구속: 한쪽만 weld된 용수철은 용접 방향으로 정렬
        #    (축방향 압축/팽창만 허용, 자유 회전 차단) ───────────────────────
        self._apply_spring_weld_orientation()

        # ── 양끝 weld 용수철: 두 끝점이 용접 축과 평행 유지(회전 금지) ──────
        self._apply_spring_both_ends_axis()

        # ── ImageBlock 자체 강체 복원 ──────────────────────────────────────
        # 충돌 충격에 둘레가 변형되면 일부만 막히고 나머지가 통과(터널링)한다.
        # 매 프레임 rest shape으로 복원해 강체를 유지 (weld된 ImageBlock 제외).
        for obj in self.objects:
            if getattr(obj, 'name', '') == 'ImageBlock' and hasattr(obj, 'apply_rigid_match'):
                wgid = getattr(obj, 'weld_group_id', None)
                if wgid in getattr(self, "_weld_rest", {}):
                    continue  # weld 그룹이 이미 처리
                obj.apply_rigid_match()

        # ── Shape matching 후 힌지 재보정 (강한 구속) ──────────────────────
        # shape matching이 힌지 파티클을 이동시켰을 수 있으므로 여러 번 강제 일치
        for _hinge_pass in range(8):
            moved = False
            for c in all_constraints:
                if getattr(c, 'style', '') != 'hinge': continue
                delta = c.p2.pos - c.p1.pos
                dist  = delta.length()
                if dist < 1e-7: continue
                inv_m1 = 0.0 if c.p1.is_static else 1.0 / c.p1.mass
                inv_m2 = 0.0 if c.p2.is_static else 1.0 / c.p2.mass
                total_w = inv_m1 + inv_m2
                if total_w < 1e-10: continue
                n_hat = delta / dist
                corr  = dist / total_w
                if not c.p1.is_static:
                    c.p1.pos     += n_hat * (corr * inv_m1)
                    c.p1.old_pos += n_hat * (corr * inv_m1)  # 속도 보존
                if not c.p2.is_static:
                    c.p2.pos     -= n_hat * (corr * inv_m2)
                    c.p2.old_pos -= n_hat * (corr * inv_m2)
                moved = True
            if not moved: break

        # ── Shape matching 후 화면 경계 재클램프 ──────────────────────────
        # 강체 복원이 파티클을 벽 밖으로 밀어낼 수 있으므로 위치만 다시 가둠.
        # weld 멤버에만 적용 (일반 파티클은 위에서 이미 반발 처리됨)
        for p in all_particles:
            if p.is_static: continue
            if id(p) not in self._weld_member_ids: continue
            if p.pos.y > self.height - p.radius:
                p.pos.y = self.height - p.radius
                if p.old_pos.y < p.pos.y: p.old_pos.y = p.pos.y  # 하강속도 제거
            if p.pos.y < p.radius:
                p.pos.y = p.radius
                if p.old_pos.y > p.pos.y: p.old_pos.y = p.pos.y
            if p.pos.x < p.radius:
                p.pos.x = p.radius
                if p.old_pos.x > p.pos.x: p.old_pos.x = p.pos.x
            if p.pos.x > self.width - p.radius:
                p.pos.x = self.width - p.radius
                if p.old_pos.x < p.pos.x: p.old_pos.x = p.pos.x

        # ── 오브젝트별 힘 누산 (constraint 전후 Δpos 기반) ───────────────────
        # tension_acc / spring_acc / int_acc / normal_acc / stress_max 갱신
        for obj in self.objects:
            ps = obj._particle_set
            max_stress = 0.0

            for c in all_constraints:
                is_spring = getattr(c, 'style', '') == 'spring'
                is_global = (c.parent == "global")

                p1_mine = id(c.p1) in ps
                p2_mine = id(c.p2) in ps

                for p, mine in [(c.p1, p1_mine), (c.p2, p2_mine)]:
                    if not mine or p.is_static: continue
                    pid = id(p)
                    if pid not in pre_pos: continue
                    delta_mag = (p.pos - pre_pos[pid]).length()
                    if delta_mag < 1e-9: continue
                    f_contrib = p.mass * delta_mag / max(dt * dt, 1e-9)

                    if is_spring:
                        obj.spring_acc += f_contrib
                    elif is_global and (p1_mine != p2_mine):
                        obj.tension_acc += f_contrib
                    elif not is_global:
                        c_parent = c.parent
                        if isinstance(c_parent, StringObj):
                            obj.tension_acc += f_contrib
                        elif isinstance(c_parent, TrueSpring):
                            obj.spring_acc += f_contrib
                        else:
                            obj.int_acc += f_contrib

                # constraint 자체의 stress 누산 → 이 obj에 속하면 누적
                if c.stress > 0 and (p1_mine or p2_mine):
                    max_stress = max(max_stress, c.stress)

            obj.stress_max = max_stress

            # ★ 수직항력: _contact_normal_impulse로 정확하게 계산
            total_nf = 0.0
            for p in obj.particles:
                pid = id(p)
                if pid in self._contact_normal_impulse:
                    total_nf += self._contact_normal_impulse[pid]
            obj.normal_acc = total_nf

            # 풀리 tension 누산
            for pc in self.pulley_constraints:
                pts_mine = [p for p in pc.pts if id(p) in ps and not p.is_static]
                for p in pts_mine:
                    pid = id(p)
                    if pid not in pre_pos: continue
                    delta_mag = (p.pos - pre_pos[pid]).length()
                    if delta_mag < 1e-9: continue
                    obj.tension_acc += p.mass * delta_mag / max(dt * dt, 1e-9)

        # 프레임 끝: 수직항력 누산기 초기화 (다음 프레임에서 새로 집계)
        self._contact_normal_impulse.clear()

    # ── XPBD 스프링 compliance ─────────────────────────────────────────────────
    @staticmethod
    def xpbd_spring_alpha(stiffness, dt):
        """
        XPBD compliant spring:
          α = 1/(k_eff · dt²),   k_eff = stiffness · K_SCALE

        ★ 재보정: 기존 K_SCALE=1e7은 너무 뻣뻣해서(기본 stiffness 0.001 →
          k_eff=1e4) 5kg 추를 매달아도 0.3px밖에 안 늘어나 사실상 강체였다.
          K_SCALE=2e4로 낮춰 실제 스프링처럼 눈에 띄게 늘어나고/수축하게 한다.
          (5kg 정적 신장 ≈ 17px, 충돌 수축 ≈ 39px, 진동 없이 안정)
            stiffness=1.0   → k_eff=2e4  (단단한 스프링)
            stiffness=0.001 → k_eff=20   (기본, 부드러운 스프링)
        """
        K_SCALE = 2e4
        k_eff = max(stiffness, 1e-6) * K_SCALE
        return 1.0 / (k_eff * max(dt * dt, 1e-12))


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────
def _same_group(p1, p2):
    par1 = p1.parent; par2 = p2.parent
    if par1 is None or par2 is None: return False
    # 문자열 부모("global")는 그룹 비교 대상 아님
    t1 = type(par1); t2 = type(par2)
    if t1 is str or t2 is str: return False
    cg1 = getattr(par1, 'collision_group', None)
    cg2 = getattr(par2, 'collision_group', None)
    if cg1 is None or cg2 is None: return False
    if cg1 == cg2: return True
    # weld_group_id가 같으면 같은 강체 → 충돌 skip
    wg1 = getattr(par1, 'weld_group_id', None)
    wg2 = getattr(par2, 'weld_group_id', None)
    if wg1 is not None and wg1 == wg2: return True
    return False

def _different_layer(p1, p2):
    par1 = p1.parent; par2 = p2.parent
    if par1 is None or par2 is None: return False
    if type(par1) is str or type(par2) is str: return False
    return getattr(par1, 'z_layer', 0) != getattr(par2, 'z_layer', 0)

def get_nearest_particle(engine, pos, radius=20):
    nearest, min_dist = None, radius
    for obj in engine.objects:
        for p in obj.particles:
            dist = p.pos.distance_to(pos)
            if dist < min_dist: min_dist, nearest = dist, p
    return nearest

def get_nearest_edge(engine, pos, threshold=15):
    pos_vec = pygame.math.Vector2(pos)
    best_point, best_edge, best_obj, best_dist = None, None, None, threshold

    for obj in engine.objects:
        if isinstance(obj, Circle):
            p = obj.particles[0]
            dist_to_center  = pos_vec.distance_to(p.pos)
            dist_to_surface = abs(dist_to_center - obj.radius)
            if dist_to_surface < best_dist:
                best_dist, best_obj, best_edge = dist_to_surface, obj, "CIRCLE"
                dir_vec = pygame.math.Vector2(1, 0) if dist_to_center == 0 \
                          else (pos_vec - p.pos).normalize()
                best_point = p.pos + dir_vec * obj.radius
            continue

        for c in obj.constraints:
            if not getattr(c, 'is_solid', False): continue
            p1, p2      = c.p1.pos, c.p2.pos
            line_vec    = p2 - p1
            line_len_sq = line_vec.length_squared()
            if line_len_sq == 0: continue
            t       = max(0, min(1, (pos_vec - p1).dot(line_vec) / line_len_sq))
            closest = p1 + line_vec * t
            dist    = pos_vec.distance_to(closest)
            if dist < best_dist:
                best_dist, best_point, best_edge, best_obj = dist, closest, c, obj

    return best_point, best_edge, best_obj