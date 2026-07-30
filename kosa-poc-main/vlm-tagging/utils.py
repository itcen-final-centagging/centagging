import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def crop_image(image: Image.Image, bbox: list) -> Image.Image:
    """
    VLM이 반환한 [ymin, xmin, ymax, xmax] (0~1000 정규화 좌표)를 기준으로
    PIL 이미지를 크롭하여 반환합니다.
    """
    width, height = image.size
    
    # 0~1000 좌표를 픽셀 좌표로 환산
    ymin = int((bbox[0] / 1000.0) * height)
    xmin = int((bbox[1] / 1000.0) * width)
    ymax = int((bbox[2] / 1000.0) * height)
    xmax = int((bbox[3] / 1000.0) * width)
    
    # 경계값 제한
    ymin = max(0, min(ymin, height - 1))
    xmin = max(0, min(xmin, width - 1))
    ymax = max(ymin + 1, min(ymax, height))
    xmax = max(xmin + 1, min(xmax, width))
    
    return image.crop((xmin, ymin, xmax, ymax))

def draw_bounding_boxes(image: Image.Image, detections: list) -> Image.Image:
    """
    detections: [{'bbox': [ymin, xmin, ymax, xmax], 'label': 'chair', 'id': 1}, ...]
    이미지 위에 바운딩 박스와 ID 라벨을 그리고 가독성 높은 형태로 반환합니다.
    """
    draw_image = image.copy()
    draw = ImageDraw.Draw(draw_image)
    width, height = draw_image.size
    
    # 뚜렷한 색상 목록 정의
    colors = ["#ff3838", "#ff9f1a", "#2ed573", "#1e90ff", "#ae11ff"]
    
    for idx, det in enumerate(detections):
        bbox = det['bbox']
        label = det.get('display_label', det['label'])
        det_id = det.get('id', idx + 1)
        
        # 픽셀 좌표 환산
        ymin = int((bbox[0] / 1000.0) * height)
        xmin = int((bbox[1] / 1000.0) * width)
        ymax = int((bbox[2] / 1000.0) * height)
        xmax = int((bbox[3] / 1000.0) * width)
        
        # 경계선 색상 선택
        color = colors[idx % len(colors)]
        
        # 바운딩 박스 그리기 (선 두께 4px)
        for i in range(4):
            draw.rectangle([xmin + i, ymin + i, xmax - i, ymax - i], outline=color)
        
        # 라벨 배경 및 텍스트 그리기
        text = f"#{det_id} {label}"
        try:
            # 기본 폰트 크기 조절 시도
            font = ImageFont.load_default()
        except:
            font = None
            
        # 텍스트 영역 계산
        text_bbox = draw.textbbox((xmin, ymin), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # 텍스트 배경 사각형 그리기
        draw.rectangle([xmin, ymin - text_height - 6, xmin + text_width + 10, ymin], fill=color)
        
        # 텍스트 그리기
        draw.text((xmin + 5, ymin - text_height - 4), text, fill="#ffffff", font=font)
        
    return draw_image
