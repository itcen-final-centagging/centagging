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
            "created_at": "2026-08-10T17:56:00+09:00",
            "scene_image_url": {
              "image_url": "https://cdn.example.com/scenes/4402.jpg",
              "origin_name": "scene_office_01.jpg"
            },
            "bbox_coord": {
              "xmin": 300,
              "xmax": 500,
              "ymin": 800,
              "ymax": 600,
            },
            "object_category": "의자",
            "confirmed_sku": {
              "sku_code": "CH-2041",
              "product_name": "에르고 메쉬 오피스체어 화이트"
            },
            "similarity_score": 92,
            "created_by": "김태깅"
          },
          {
            "result_id": 8790,
            "created_at": "2026-08-04T11:20:00+09:00",
            "scene_origin_name": "scene_office_01.jpg",
            "bbox_coord": {
              "xmin": 500,
              "xmax": 800,
              "ymin": 900,
              "ymax": 300,
            },
            "object_category": "벽 선반",
            "confirmed_sku": {
              "sku_code": "SH-8801",
              "product_name": "월 플로팅 선반 900 화이트"
            },
            "similarity_score": None,
            "created_by": "김태깅"
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
        "created_at": "2026-08-10T17:56:00+09:00",
        "created_by": "김태깅" ,
        "similarity_score": 92,

        "scene_image": {
          "image_url": "https://cdn.example.com/scenes/4402.jpg",
          "origin_name": "scene_office_01.jpg"
        },

        "detected_object": {
          "bbox_coord": { "xmin": 262, "ymin": 300, "xmax": 681, "ymax": 890 },
          "category": "의자",
          "sub_category": "오피스체어",
          "attrs": [
            { "label": "소재", "value": "메쉬 · 패브릭 · 알루미늄" },
            { "label": "색상", "value": "화이트 / 차콜" },
            { "label": "형태", "value": "하이백" },
            { "label": "구조", "value": "5스타 캐스터" },
            { "label": "공간", "value": "홈오피스" }
          ],
          "mood_summary": "밝은 자연광이 드는 미니멀한 홈오피스에 어울리는 화이트 톤 워크체어입니다.",
          "mood_tags": ["미니멀", "내추럴", "홈오피스", "밝은 톤"]
        },

        "confirmed_sku": {
          "sku_code": "CH-2041",
          "product_name": "에르고 메쉬 오피스체어 화이트",
          "brand": "센터퍼니처",
          "price": 249000,
          "image_url": "https://cdn.example.com/skus/CH-2041_main.jpg",
          "category": "의자",
          "sub_category": "오피스체어",
          "attrs": [
            { "label": "소재", "value": "메쉬 · 패브릭 · 알루미늄" },
            { "label": "색상", "value": "화이트 / 차콜" },
            { "label": "형태", "value": "하이백" },
            { "label": "구조", "value": "5스타 캐스터" },
            { "label": "공간", "value": "홈오피스" }
          ]
        }
      }
    }