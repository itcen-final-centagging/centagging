import os
import json
import logging
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv

# .env 로드 (현재 디렉토리에서 상위로 거슬러 올라가며 탐색)
# 도커 실행 시에는 compose 의 env_file 로 이미 주입되므로 override 하지 않습니다.
load_dotenv(find_dotenv(usecwd=True), override=False)

# 로깅 설정 (포맷 정의 및 콘솔 출력 설정)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - (%(filename)s:%(lineno)d) - %(message)s'
)
logger = logging.getLogger("VLMClient")

# API Key 로드 함수
def load_api_key():
    """
    환경 변수에서 Gemini API Key 를 로드합니다.
    (.env 파일은 모듈 상단의 load_dotenv 로 이미 환경 변수에 반영됩니다.)
    """
    return os.environ.get("GEMINI_API_KEY")

class VLMClient:
    def __init__(self, use_mock=False):
        self.use_mock = use_mock
        # API Key 로드 (환경 변수 / .env)
        self.api_key = load_api_key()
        
        if not self.use_mock and self.api_key:
            # 신형 google-genai SDK 클라이언트 초기화 및 gemini-3.5-flash 지정
            logger.info("Initializing VLMClient with Gemini API.")
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.model_name = 'gemini-3.5-flash'
                logger.info(f"VLMClient initialized successfully. Model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")
                self.use_mock = True
        else:
            logger.warning("No API Key or mock mode is requested. Running in offline/mock mode.")
            self.use_mock = True
            
    def detect_objects(self, image: Image.Image) -> list:
        """
        연출샷 이미지에서 가구 객체들을 검출하고 [ymin, xmin, ymax, xmax] 좌표 목록을 반환합니다.
        """
        if self.use_mock:
            logger.info("[Mock Mode] Detecting objects (Returning static grounding coordinates).")
            return self._get_mock_detections()
            
        prompt = """
        Analyze the image and locate all furniture items (specifically office chairs, office desks, desk lamps, or filing cabinets).
        For each detected item, return the bounding box coordinates as [ymin, xmin, ymax, xmax] in a normalized scale of 0 to 1000.
        You must output the result strictly in JSON format matching this schema:
        {
          "detections": [
            {"label": "chair", "bbox": [ymin, xmin, ymax, xmax]},
            {"label": "desk", "bbox": [ymin, xmin, ymax, xmax]},
            {"label": "lamp", "bbox": [ymin, xmin, ymax, xmax]}
          ]
        }
        """
        
        logger.info("===== VLM Object Detection Request Started =====")
        logger.info(f"Target Image Size: {image.size}")
        logger.info(f"API Endpoint Call -> Model: {self.model_name}")
        
        try:
            # 신형 SDK 규격 호출
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[image, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            logger.info("VLM Object Detection API Response received.")
            logger.debug(f"Raw Response: {response.text}")
            
            data = json.loads(response.text)
            detections = data.get("detections", [])
            logger.info(f"Successfully parsed detections. Total objects found: {len(detections)}")
            for det in detections:
                logger.info(f" -> Found label: '{det.get('label')}' with bbox: {det.get('bbox')}")
            
            return detections
        except Exception as e:
            logger.error(f"Gemini API Error (Detection) failed: {e}. Falling back to mock data.", exc_info=True)
            return self._get_mock_detections()

    def evaluate_matching(self, cropped_image: Image.Image, sku_data: dict) -> dict:
        """
        크롭된 가구 이미지 패치와 5종의 SKU 단품 라이브러리를 비교 분석하여 매칭 결과와 XAI 채점표를 반환합니다.
        """
        if self.use_mock:
            logger.info("[Mock Mode] Evaluating SKU matching.")
            return self._get_mock_matching(sku_data, cropped_image)

        prompt = """
        You are a highly precise industrial QA inspector. Compare the 'Target Cropped Image' with the 5 reference 'SKU Images' provided.
        Evaluate the likelihood of matching for each of the 5 SKU options.
        For each SKU, calculate a match score out of 100 based on these four strict rubrics:
        1. "structure_score" (max 30): Geometry, shape, structural frames, wheels, armrests.
        2. "color_score" (max 30): Frame colors, fabric/leather colors, materials consistency.
        3. "detail_score" (max 20): Fine structures like lever knobs, dial locations, mesh pattern density.
        4. "context_score" (max 20): If the object is partially obscured/blocked, how logical is the continuation of its hidden parts.
        
        A total score of 70 or above is considered "Matched". Otherwise, it is "Rejected".
        Specifically, check:
        - If the target is the white chair, reject the all-black chair (sku_chair_black) and explain that the color frame is completely different.
        - If the target does not contain the cabinet, reject sku_cabinet and state that the object is not present.
        
        You must return the result strictly in JSON format matching this schema:
        {
          "evaluations": [
            {
              "sku_id": "sku_chair",
              "status": "Matched" or "Rejected",
              "total_score": 98,
              "breakdown": {
                "structure": 30,
                "color": 28,
                "detail": 20,
                "context": 20
              },
              "xai_reason": "Provide a detailed natural language explanation of why this match succeeded or failed."
            },
            ... (repeat for all 5 SKUs)
          ]
        }
        """

        logger.info(f"===== VLM SKU Matching Request Started =====")
        logger.info(f"Target Cropped Image Size: {cropped_image.size}")
        logger.info(f"Reference SKU Catalog Count: {len(sku_data)}")
        
        try:
            input_contents = [cropped_image]
            for sku_id, info in sku_data.items():
                input_contents.append(f"SKU ID: {sku_id}")
                input_contents.append(info['image'])
                
            input_contents.append(prompt)
            
            logger.info(f"API Endpoint Call -> Model: {self.model_name}")
            # 신형 SDK 규격 호출
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=input_contents,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            logger.info("VLM SKU Matching API Response received.")
            logger.debug(f"Raw Response: {response.text}")
            
            data = json.loads(response.text)
            evaluations = data.get("evaluations", [])
            
            best_sku = None
            max_score = -1
            
            for ev in evaluations:
                if ev['status'] == "Matched" and ev['total_score'] > max_score:
                    max_score = ev['total_score']
                    best_sku = ev
            
            logger.info(f"Evaluation complete. Best matched SKU: '{best_sku['sku_id'] if best_sku else 'Rejected'}' (Score: {max_score if best_sku else 0})")
            
            return {
                "best_sku": best_sku['sku_id'] if best_sku else "Rejected",
                "score": max_score if best_sku else 0,
                "all_evaluations": {ev['sku_id']: ev for ev in evaluations}
            }
            
        except Exception as e:
            logger.error(f"Gemini API Error (Matching) failed: {e}. Falling back to mock data.", exc_info=True)
            return self._get_mock_matching(sku_data, cropped_image)

    # --- MOCK DATA GENERATION FOR OFFLINE / FALLBACK ---
    def _get_mock_detections(self) -> list:
        return [
            {"label": "chair", "bbox": [345, 230, 995, 570], "id": 1, "display_label": "의자 (Chair)"},
            {"label": "desk", "bbox": [420, 210, 970, 856], "id": 2, "display_label": "책상 (Desk)"},
            {"label": "lamp", "bbox": [190, 650, 475, 846], "id": 3, "display_label": "조명 (Lamp)"}
        ]

    def _get_mock_matching(self, sku_data: dict, cropped_image: Image.Image) -> dict:
        width, height = cropped_image.size
        ratio = width / height
        
        best_sku = "Rejected"
        score = 0
        evals = []
        
        if ratio > 1.2:  # 책상
            best_sku = "sku_desk"
            score = 95
            evals = [
                {"sku_id": "sku_desk", "status": "Matched", "total_score": 95, 
                 "breakdown": {"structure": 28, "color": 29, "detail": 18, "context": 20},
                 "xai_reason": "원목 상판 재질의 질감과 색상 정합도가 95% 이상 일치하며, 흰색 철제 다리 디자인도 기준 SKU와 동일합니다."},
                {"sku_id": "sku_chair", "status": "Rejected", "total_score": 12, 
                 "breakdown": {"structure": 5, "color": 5, "detail": 2, "context": 0},
                 "xai_reason": "대상 이미지는 직사각형 판 형태의 책상이나, 기준 SKU는 등받이가 있는 의자이므로 불일치합니다."},
                {"sku_id": "sku_chair_black", "status": "Rejected", "total_score": 10, 
                 "breakdown": {"structure": 5, "color": 3, "detail": 2, "context": 0},
                 "xai_reason": "대상 이미지는 오크색 원목 책상이나, 기준 SKU는 올 블랙 의자이므로 카테고리가 다릅니다."},
                {"sku_id": "sku_lamp", "status": "Rejected", "total_score": 5, 
                 "breakdown": {"structure": 2, "color": 2, "detail": 1, "context": 0},
                 "xai_reason": "기하학적 형태가 책상 스탠드 조명과 전혀 부합하지 않습니다."},
                {"sku_id": "sku_cabinet", "status": "Rejected", "total_score": 18, 
                 "breakdown": {"structure": 8, "color": 5, "detail": 5, "context": 0},
                 "xai_reason": "서랍장 형태의 수납 구조가 아닌 평평한 상판 테이블 구조이므로 매칭에 실패했습니다."}
            ]
        elif ratio < 0.8:  # 조명
            best_sku = "sku_lamp"
            score = 93
            evals = [
                {"sku_id": "sku_lamp", "status": "Matched", "total_score": 93, 
                 "breakdown": {"structure": 28, "color": 27, "detail": 18, "context": 20},
                 "xai_reason": "매트한 검은색 메탈 파이프의 구부러진 각도 조절형 암 구조 및 갓 모양이 스탠드 조명 SKU와 정확히 일치합니다."},
                {"sku_id": "sku_chair", "status": "Rejected", "total_score": 8, 
                 "breakdown": {"structure": 3, "color": 2, "detail": 3, "context": 0},
                 "xai_reason": "대상은 금속 스탠드 조명이나, 해당 SKU는 바퀴와 쿠션이 있는 사무용 의자입니다."},
                {"sku_id": "sku_chair_black", "status": "Rejected", "total_score": 15, 
                 "breakdown": {"structure": 5, "color": 8, "detail": 2, "context": 0},
                 "xai_reason": "동일한 검은색 소재를 공유하지만, 형태가 의자와 조명으로 근본적인 구조 차이를 보입니다."},
                {"sku_id": "sku_desk", "status": "Rejected", "total_score": 5, 
                 "breakdown": {"structure": 2, "color": 2, "detail": 1, "context": 0},
                 "xai_reason": "원목 테이블 상판 프레임과의 기하학적 매핑률이 존재하지 않습니다."},
                {"sku_id": "sku_cabinet", "status": "Rejected", "total_score": 4, 
                 "breakdown": {"structure": 1, "color": 2, "detail": 1, "context": 0},
                 "xai_reason": "철제 서랍 캐비닛의 3단 구조가 보이지 않고 얇은 힌지 구조만 감지되므로 기각합니다."}
            ]
        else:  # 의자 (ratio 0.8 ~ 1.2)
            best_sku = "sku_chair"
            score = 98
            evals = [
                {"sku_id": "sku_chair", "status": "Matched", "total_score": 98, 
                 "breakdown": {"structure": 30, "color": 28, "detail": 20, "context": 20},
                 "xai_reason": "흰색 사출 플라스틱 프레임 구조와 검은색 메쉬 망 등받이, 그리고 흰색 쿠션이 SKU와 완벽히 겹칩니다. 다리가 책상 하부에 살짝 가려졌으나(오클루전), 공간적 위치와 은색 오성발 실루엣을 감안할 때 맥락적으로 매칭이 명확합니다."},
                {"sku_id": "sku_chair_black", "status": "Rejected", "total_score": 45, 
                 "breakdown": {"structure": 28, "color": 5, "detail": 12, "context": 0},
                 "xai_reason": "[유사 카테고리 기각] 의자의 기하학적 형태(헤드레스트, 요추 지지대, 암레스트 곡선)는 거의 동일하지만, 연출샷 속 의자는 흰색 바디인 반면 이 SKU는 전체가 올 블랙 모델이므로 색상 불일치로 엄격히 기각합니다."},
                {"sku_id": "sku_desk", "status": "Rejected", "total_score": 8, 
                 "breakdown": {"structure": 3, "color": 3, "detail": 2, "context": 0},
                 "xai_reason": "대상 이미지는 인체공학적 의자이나, 기준 SKU는 원목 책상이므로 불일치합니다."},
                {"sku_id": "sku_lamp", "status": "Rejected", "total_score": 3, 
                 "breakdown": {"structure": 1, "color": 1, "detail": 1, "context": 0},
                 "xai_reason": "스탠드 조명과 의자 간의 형태학적 일치성이 전혀 없습니다."},
                {"sku_id": "sku_cabinet", "status": "Rejected", "total_score": 5, 
                 "breakdown": {"structure": 2, "color": 2, "detail": 1, "context": 0},
                 "xai_reason": "화이트 수납 서랍장 캐비닛의 3단 도어 라인이 검출되지 않아 매칭을 거부합니다."}
            ]

        return {
            "best_sku": best_sku,
            "score": score,
            "all_evaluations": {ev['sku_id']: ev for ev in evals}
        }
