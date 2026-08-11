from fastapi import APIRouter

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/results")
def get_tagging_history():
    return {
      "status": "success",
      "data": {
        "items": [
          {
            "result_id": 8801,
            "similarity_score": 92,
            "created_by": "김태깅",
            "created_at": "2026-08-10T17:56:00+09:00",
            "scene_image": {
              "image_url": "/uploads/scene-images/9f2c.jpg",
              "origin_name": "scene_office_01.jpg",
              "bbox": { "xmin": 262, "ymin": 300, "xmax": 681, "ymax": 890 }
            }
          }
        ]
      }
    }


@router.get("/results/{result_id}")
def get_tagging_history(result_id):
    return {
      "status": "success",
      "data": {
        "result_id": 8801,
        "created_by": "김태깅",
        "created_at": "2026-08-10T17:56:00+09:00",
        "similarity_score": 92,
        "scene_image": {
          "image_url": "/uploads/scene-images/9f2c.jpg",
          "origin_name": "scene_office_01.jpg"
        },
        "detected_object": {
          "category": "의자",
          "sub_category": "학생·사무용의자",
          "attrs": { "color": "화이트", "material": "메쉬" },
          "bbox": { "xmin": 262, "ymin": 300, "xmax": 681, "ymax": 890 },
          "vlm_mood": {
            "summary": "밝은 자연광이 드는 미니멀한 홈오피스에 어울리는 화이트 톤 워크체어입니다.",
            "tags": ["미니멀", "내추럴", "홈오피스", "밝은 톤"]
          }
        },
        "matched_sku": {
          "sku_code": "CHR-2041",
          "product_name": "에르고 메쉬 오피스체어 화이트",
          "brand": "센터퍼니처",
          "price": 249000,
          "image_url": "/uploads/sku-images/CHR-2041_main.jpg",
          "category": "의자",
          "sub_category": "학생·사무용의자",
          "attrs": { "color": "화이트", "material": "메쉬" }
        },
        "xai_result": {
          "summary": "등받이 곡률과 헤드레스트 형태가 거의 동일하고 색상까지 일치합니다.",
          "criteria": [
            { "label": "구조", "score": 29, "comment": "등받이 곡률·암레스트 각도가 일치합니다." },
            { "label": "색상", "score": 28, "comment": "화이트 바디와 차콜 메쉬 조합이 같습니다." },
            { "label": "디테일", "score": 17, "comment": "5스타 캐스터 형태가 유사합니다." },
            { "label": "맥락", "score": 18, "comment": "홈오피스 연출과 사용 공간이 맞습니다." }
          ]
        }
      }
    }