/**
 * SKU 카탈로그 속성(attrs) 표시용 라벨/순서 정의입니다.
 *
 * 속성 목록 자체는 백엔드 스펙 사본인 `catalogSpec.ts`에서 파생시켜,
 * 카테고리별 속성 정의가 두 곳으로 갈라지지 않도록 합니다.
 */

import {
  COMMON_ATTRIBUTE,
  PRODUCT_ATTRIBUTE,
} from '@/features/tagging/constants/catalogSpec';

export const COMMON_ATTRIBUTE_KEYS: string[] = Object.keys(COMMON_ATTRIBUTE);

export const ATTRIBUTE_LABELS: Record<string, string> = {
  base_type: '베이스 유형',
  bed_type: '침대 유형',
  brand: '브랜드',
  chair_type: '의자 유형',
  color: '색상',
  door_type: '도어 유형',
  drawer_count: '단수',
  features: '특징',
  firmness: '경도',
  frame_material: '프레임 소재',
  frame_type: '프레임 유형',
  has_armrest: '팔걸이 유무',
  has_backrest: '등받이 유무',
  has_drawer: '서랍 유무',
  has_frame: '프레임 유무',
  has_headboard: '헤드보드 유무',
  has_headrest: '헤드레스트 유무',
  has_legs: '다리 유무',
  has_mirror: '거울 유무',
  has_stool: '스툴 포함 여부',
  has_storage: '수납 유무',
  has_wheels: '바퀴 유무',
  head_type: '헤드 유형',
  installation_type: '설치 방식',
  layout_type: '레이아웃 유형',
  leg_type: '다리 유형',
  length: '길이',
  level_count: '단수',
  material: '소재',
  mattress_type: '매트리스 유형',
  mobility_type: '이동 방식',
  pattern: '패턴',
  product_type: '제품 유형',
  seating_capacity: '인승수',
  selling_price: '판매가',
  shape: '형태',
  shelf_count: '단수',
  shelf_type: '선반 유형',
  size: '사이즈',
  sofa_type: '소파 유형',
  storage_features: '수납 특징',
  storage_type: '유형',
  style: '스타일',
  thickness: '두께',
  top_material: '상판 소재',
  tv_stand_type: '유형',
  vanity_type: '유형',
  wardrobe_type: '옷장 유형',
  wood_tone: '우드톤',
};

/** 대분류별로 표기할 카테고리 전용 속성 순서입니다. */
export const CATEGORY_ATTRIBUTE_FIELDS: Record<string, string[]> =
  Object.fromEntries(
    Object.entries(PRODUCT_ATTRIBUTE).map(([category, attributes]) => [
      category,
      Object.keys(attributes),
    ]),
  );
