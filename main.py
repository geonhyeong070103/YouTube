import pygame
import sys

# 1. Pygame 초기화
pygame.init()

# 2. 화면 크기 및 타이틀 설정
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Pygame 기본 예제")

# 3. 색상 정의 (RGB)
WHITE = (255, 255, 255)
RED = (255, 0, 0)

# 4. 플레이어(사각형) 속성 설정
rect_width = 50
rect_height = 50
# 화면 정중앙에 위치하도록 초기화
rect_x = (SCREEN_WIDTH // 2) - (rect_width // 2)
rect_y = (SCREEN_HEIGHT // 2) - (rect_height // 2)
rect_speed = 5

# 5. 프레임 레이트 설정을 위한 Clock 객체 생성
clock = pygame.time.Clock()

# 메인 게임 루프
running = True
while running:
    # FPS 제한 (초당 60프레임)
    clock.tick(60)

    # --- 이벤트 처리 영역 ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:  # 창 닫기 버튼을 눌렀을 때
            running = False

    # --- 키 입력 처리 영역 (연속 입력 지원) ---
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        rect_x -= rect_speed
    if keys[pygame.K_RIGHT]:
        rect_x += rect_speed
    if keys[pygame.K_UP]:
        rect_y -= rect_speed
    if keys[pygame.K_DOWN]:
        rect_y += rect_speed

    # --- 경계값 조건 처리 (화면 밖으로 탈출 방지) ---
    if rect_x < 0:
        rect_x = 0
    elif rect_x > SCREEN_WIDTH - rect_width:
        rect_x = SCREEN_WIDTH - rect_width

    if rect_y < 0:
        rect_y = 0
    elif rect_y > SCREEN_HEIGHT - rect_height:
        rect_y = SCREEN_HEIGHT - rect_height

    # --- 화면 그리기 영역 ---
    screen.fill(WHITE)  # 배경을 흰색으로 채우기 (잔상 제거)

    # 화면에 빨간색 사각형 그리기
    pygame.draw.rect(screen, RED, (rect_x, rect_y, rect_width, rect_height))

    # 작업한 내용을 실제 모니터 화면에 반영
    pygame.display.flip()

# Pygame 종료
pygame.quit()
sys.exit()