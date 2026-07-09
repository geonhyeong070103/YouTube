import pygame
import math
import os
import random

def run_intro(screen, clock, width, height):
    intro_font = pygame.font.SysFont("malgungothic, applegothic, sans", 55, bold=True)
    sub_font   = pygame.font.SysFont("malgungothic, applegothic, sans", 16, bold=True)

    logo_img = None
    if os.path.exists('logo.png'):
        try:
            logo_raw = pygame.image.load('logo.png').convert_alpha()
            logo_img = pygame.transform.smoothscale(logo_raw, (140, 140))
        except Exception as e:
            print(f"로고 이미지를 불러오지 못했습니다: {e}")

    particles = []
    for _ in range(35):
        particles.append({
            'pos': pygame.math.Vector2(random.randint(0, width), random.randint(0, height)),
            'vel': pygame.math.Vector2(random.uniform(-0.4, 0.4), random.uniform(-0.4, 0.4)),
            'radius': random.randint(3, 6),
            'color': (210, 215, 225)
        })

    # ── 최적화: 단일 오버레이 Surface 재사용 (매 프레임 새로 생성 X) ──────────
    line_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    fade_surf = pygame.Surface((width, height))
    fade_surf.fill((255, 255, 255))

    alpha = 255
    state = "FADE_IN"
    running = True
    animation_time = 0.0

    while running:
        animation_time += 0.04

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if state == "WAIT":
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    state = "FADE_OUT"

        for p in particles:
            p['pos'] += p['vel']
            if p['pos'].x < 0 or p['pos'].x > width:  p['vel'].x *= -1
            if p['pos'].y < 0 or p['pos'].y > height:  p['vel'].y *= -1

        screen.fill((255, 255, 255))

        # ── 최적화: line_surf 한 번만 clear 후 모든 선을 그림 ────────────────
        line_surf.fill((0, 0, 0, 0))
        for i, p in enumerate(particles):
            pygame.draw.circle(screen, p['color'],
                               (int(p['pos'].x), int(p['pos'].y)), p['radius'])
            for j in range(i + 1, len(particles)):
                p2   = particles[j]
                dist = p['pos'].distance_to(p2['pos'])
                if dist < 140:
                    line_alpha = int((1.0 - dist / 140) * 60)
                    pygame.draw.line(line_surf, (180, 190, 210, line_alpha),
                                     p['pos'], p2['pos'], 1)
        screen.blit(line_surf, (0, 0))

        logo_y_offset = 0
        if logo_img:
            floating_y = int(math.sin(animation_time * 0.8) * 8)
            logo_rect  = logo_img.get_rect(
                center=(width // 2, height // 2 - 90 + floating_y))
            screen.blit(logo_img, logo_rect)
            logo_y_offset = 55

        title_text = intro_font.render("Zenith Motion", True, (33, 37, 43))
        title_rect = title_text.get_rect(
            center=(width // 2, height // 2 + logo_y_offset))
        screen.blit(title_text, title_rect)

        breathing_alpha = int((math.sin(animation_time * 1.5) + 1.0) * 100) + 40
        sub_text  = sub_font.render("CLICK OR PRESS ANY KEY TO START", True, (130, 140, 155))
        sub_surf  = pygame.Surface(sub_text.get_size(), pygame.SRCALPHA)
        sub_surf.blit(sub_text, (0, 0))
        sub_surf.fill((255, 255, 255, breathing_alpha),
                      special_flags=pygame.BLEND_RGBA_MULT)
        sub_rect  = sub_surf.get_rect(
            center=(width // 2, height // 2 + logo_y_offset + 75))
        screen.blit(sub_surf, sub_rect)

        if state == "FADE_IN":
            alpha -= 15
            if alpha <= 0:
                alpha = 0
                state = "WAIT"
            fade_surf.set_alpha(alpha)
            screen.blit(fade_surf, (0, 0))
        elif state == "FADE_OUT":
            alpha += 25
            if alpha >= 255:
                alpha = 255
                running = False
            fade_surf.set_alpha(alpha)
            screen.blit(fade_surf, (0, 0))

        pygame.display.flip()
        clock.tick(60)