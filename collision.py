"""
collision.py — SAT(Separating Axis Theorem) 충돌 검사 모듈

engine.py에서 분리된 폴리곤 충돌 헬퍼들.

★ 업그레이드: 오목(concave) 폴리곤 지원
  기존에는 HShape/TShape/PolygonShape의 오목한 외곽선(render_particles)을
  볼록 폴리곤처럼 SAT에 넘겨서, H자 홈 안에 물체가 들어가면
  잘못 밀려나는 문제가 있었다.
  이제 get_convex_hulls()가 물체를 볼록 조각(convex hull) 리스트로 분해하고,
  sat_collide_objects()가 모든 조각 쌍에 대해 SAT를 돌려
  실제로 겹친 부분만 정확히 충돌 처리한다.
    - CompoundShape(HShape/TShape): box_groups의 서브박스별 검사
    - PolygonShape: hull_indices가 정의돼 있으면 그 그룹별 검사
    - 그 외(Box/Triangle 등 볼록 도형): 단일 hull로 기존과 동일하게 동작
"""
import pygame


# ─────────────────────────────────────────────────────────────────────────────
# 기본 SAT 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _sat_project(verts, axis):
    """폴리곤 꼭짓점을 축에 투영해 [min, max] 반환."""
    dots = [v.dot(axis) for v in verts]
    return min(dots), max(dots)


def _sat_overlap(minA, maxA, minB, maxB):
    """두 투영 구간의 겹침 크기 반환. 분리되면 None."""
    o = min(maxA, maxB) - max(minA, minB)
    return o if o > 0 else None


def _sat_test(vertsA, vertsB):
    """
    SAT로 두 볼록 폴리곤의 충돌 검사.
    충돌 시: (True, 최소분리축 normal Vector2, 침투깊이 float)
    분리 시: (False, None, 0)
    normal은 A→B 분리 방향 (A를 밀어내는 방향).
    """
    best_depth = float('inf')
    best_normal = None

    for verts in (vertsA, vertsB):
        n = len(verts)
        for i in range(n):
            edge = verts[(i + 1) % n] - verts[i]
            # 엣지의 법선 (오른쪽 수직)
            axis = pygame.math.Vector2(-edge.y, edge.x)
            axis_len = axis.length()
            if axis_len < 1e-8:
                continue
            axis /= axis_len

            minA, maxA = _sat_project(vertsA, axis)
            minB, maxB = _sat_project(vertsB, axis)
            overlap = _sat_overlap(minA, maxA, minB, maxB)
            if overlap is None:
                return False, None, 0.0

            if overlap < best_depth:
                best_depth = overlap
                best_normal = axis

    if best_normal is None:
        return False, None, 0.0

    # normal 방향: A 중심에서 B 중심으로
    cA = sum(vertsA, pygame.math.Vector2()) / len(vertsA)
    cB = sum(vertsB, pygame.math.Vector2()) / len(vertsB)
    if (cB - cA).dot(best_normal) < 0:
        best_normal = -best_normal

    return True, best_normal, best_depth


def _segment_intersect(p1, p2, p3, p4):
    """두 선분 p1-p2, p3-p4의 교차 여부와 파라미터 t 반환."""
    d1 = p2 - p1; d2 = p4 - p3
    cross = d1.x * d2.y - d1.y * d2.x
    if abs(cross) < 1e-10:
        return False, 1.0
    t = ((p3.x - p1.x) * d2.y - (p3.y - p1.y) * d2.x) / cross
    u = ((p3.x - p1.x) * d1.y - (p3.y - p1.y) * d1.x) / cross
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return True, max(0.0, t - 0.01)
    return False, 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 오브젝트 → 꼭짓점 변환
# ─────────────────────────────────────────────────────────────────────────────

def _poly_get_verts(obj):
    """오브젝트의 충돌용 꼭짓점 리스트 반환 (Vector2 list). (하위 호환용)"""
    from objects import Box, Triangle, RightTriangle, Circle
    if isinstance(obj, Circle):
        return None   # 원은 별도 처리
    if isinstance(obj, Box):
        return [p.pos for p in obj.particles[:4]]
    if isinstance(obj, (Triangle, RightTriangle)):
        return [p.pos for p in obj.particles[:3]]
    rp = getattr(obj, 'render_particles', None)
    if rp:
        return [p.pos for p in rp]
    return None


def get_convex_hulls(obj):
    """
    오브젝트를 볼록 조각(convex hull) 리스트로 분해해서 반환.
    반환: [[Vector2, ...], ...]  또는 None(원/미지원).

    분해 우선순위:
    1. box_groups (CompoundShape: HShape/TShape) → 서브박스별 hull
    2. hull_indices (PolygonShape 등) → render_particles 인덱스 그룹별 hull
    3. 볼록 단일 도형 → [_poly_get_verts(obj)]
    """
    from objects import Circle
    if isinstance(obj, Circle):
        return None

    # 1. CompoundShape: 볼록 서브박스 그룹
    box_groups = getattr(obj, 'box_groups', None)
    if box_groups:
        hulls = []
        for corners in box_groups:
            if len(corners) >= 3:
                hulls.append([p.pos for p in corners])
        if hulls:
            return hulls

    # 2. PolygonShape 등: 인덱스 기반 볼록 분해
    hull_indices = getattr(obj, 'hull_indices', None)
    rp = getattr(obj, 'render_particles', None)
    if hull_indices and rp:
        hulls = []
        for idx_group in hull_indices:
            if len(idx_group) >= 3 and max(idx_group) < len(rp):
                hulls.append([rp[i].pos for i in idx_group])
        if hulls:
            return hulls

    # 3. 볼록 단일 도형
    verts = _poly_get_verts(obj)
    return [verts] if verts else None


def sat_collide_objects(objA, objB):
    """
    두 오브젝트의 볼록 조각 쌍 전체에 SAT를 수행하고,
    가장 깊게 침투한 충돌 하나를 반환.
    반환: (hit bool, normal Vector2|None, depth float)
    normal은 A→B 분리 방향 (A를 normal 반대로 밀어내는 방향).
    """
    hullsA = get_convex_hulls(objA)
    hullsB = get_convex_hulls(objB)
    if not hullsA or not hullsB:
        return False, None, 0.0

    # ── AABB 사전 컷오프 (조각 수가 많은 오목 도형의 SAT 비용 절감) ──
    def _aabb(h):
        xs = [v.x for v in h]; ys = [v.y for v in h]
        return min(xs), min(ys), max(xs), max(ys)
    boxesA = [_aabb(h) for h in hullsA]
    boxesB = [_aabb(h) for h in hullsB]
    # 오브젝트 레벨 AABB
    oA = (min(b[0] for b in boxesA), min(b[1] for b in boxesA),
          max(b[2] for b in boxesA), max(b[3] for b in boxesA))
    oB = (min(b[0] for b in boxesB), min(b[1] for b in boxesB),
          max(b[2] for b in boxesB), max(b[3] for b in boxesB))
    if oA[2] < oB[0] or oB[2] < oA[0] or oA[3] < oB[1] or oB[3] < oA[1]:
        return False, None, 0.0

    best_hit, best_normal, best_depth = False, None, 0.0
    for hA, bA in zip(hullsA, boxesA):
        for hB, bB in zip(hullsB, boxesB):
            if bA[2] < bB[0] or bB[2] < bA[0] or bA[3] < bB[1] or bB[3] < bA[1]:
                continue
            hit, normal, depth = _sat_test(hA, hB)
            if hit and depth > best_depth:
                best_hit, best_normal, best_depth = True, normal, depth
    return best_hit, best_normal, best_depth