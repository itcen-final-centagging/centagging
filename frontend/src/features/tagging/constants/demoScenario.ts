import type { FurnitureObject, SkuCandidate } from '../types';

export const DEMO_IMAGE_URL = '/sku-images/13/main.png';

const DEMO_SKUS: SkuCandidate[] = [
  {
    attrs: {
      color: '브라운',
      has_armrest: '있음',
      has_headrest: '없음',
      has_legs: '있음',
      has_stool: '없음',
      material: '패브릭',
      pattern: '무지',
      sofa_type: '소파베드',
      style: '모던',
    },
    category: '소파',
    color: '브라운',
    imageUrl: '/sku-images/13/main.png',
    kind: 'sofa',
    material: '패브릭',
    matchRank: 1,
    metadataScore: 95,
    name: '카페 패브릭 2인 접이식 소파베드',
    rubric: {
      breakdown: { structure: 30, color: 29, detail: 18, context: 17 },
      status: 'Matched',
      totalScore: 94,
      xaiReason:
        '패브릭 소파베드의 낮은 팔걸이, 쿠션 분할선과 브라운 계열 색상이 객체 영역과 일치합니다.',
    },
    score: 94,
    size: '2인용',
    sku: 'SOFA-6F976FF8',
    vectorScore: 0.96,
    vlmMood: {
      summary: '따뜻한 우드 인테리어에 어울리는 브라운 패브릭 소파베드',
      tags: ['모던', '내추럴', '패브릭'],
    },
    xaiReason:
      '객체의 형태와 색상, 공간 내 배치가 가장 높은 유사도를 보였습니다.',
    xaiResult: {
      criteria: [
        {
          label: '형태',
          score: 30,
          comment: '낮은 등받이와 넓은 좌방석이 유사합니다.',
        },
        {
          label: '색상',
          score: 29,
          comment: '브라운 패브릭 색상이 일치합니다.',
        },
      ],
      summary: '소파베드 구조와 색상 특징이 이미지의 객체와 가장 유사합니다.',
    },
  },
  {
    attrs: {
      color: '그레이',
      has_armrest: '있음',
      has_headrest: '없음',
      has_legs: '있음',
      has_stool: '없음',
      material: '패브릭',
      pattern: '무지',
      sofa_type: '소파베드',
      style: '모던',
    },
    category: '소파',
    color: '그레이',
    imageUrl: '/sku-images/14/main.png',
    kind: 'sofa',
    material: '패브릭',
    matchRank: 2,
    metadataScore: 87,
    name: '카페 패브릭 2인 접이식 소파베드',
    rubric: {
      breakdown: { structure: 30, color: 15, detail: 18, context: 17 },
      status: 'Matched',
      totalScore: 80,
      xaiReason: '구조는 유사하지만 객체의 브라운 색상과 차이가 있습니다.',
    },
    score: 80,
    size: '2인용',
    sku: 'SOFA-85B649EF',
    vectorScore: 0.87,
    vlmMood: {
      summary: '차분한 그레이 패브릭 소파베드',
      tags: ['모던', '그레이', '패브릭'],
    },
    xaiReason: '구조적 유사도는 높지만 색상 조건이 일부 다릅니다.',
    xaiResult: {
      criteria: [
        { label: '형태', score: 30, comment: '소파베드 구조가 유사합니다.' },
        {
          label: '색상',
          score: 15,
          comment: '그레이와 브라운의 색상 차이가 있습니다.',
        },
      ],
      summary: '형태는 유사하나 색상 차이로 두 번째 후보입니다.',
    },
  },
  {
    attrs: {
      color: '그린',
      has_armrest: '있음',
      has_headrest: '없음',
      has_legs: '있음',
      has_stool: '없음',
      material: '패브릭',
      pattern: '무지',
      sofa_type: '소파베드',
      style: '모던',
    },
    category: '소파',
    color: '그린',
    imageUrl: '/sku-images/15/main.png',
    kind: 'sofa',
    material: '패브릭',
    matchRank: 3,
    metadataScore: 75,
    name: '카페 패브릭 2인 접이식 소파베드',
    rubric: {
      breakdown: { structure: 29, color: 8, detail: 17, context: 16 },
      status: 'Matched',
      totalScore: 70,
      xaiReason: '형태는 비슷하지만 초록색 계열이라 색상 일치도가 낮습니다.',
    },
    score: 70,
    size: '2인용',
    sku: 'SOFA-64A314D0',
    vectorScore: 0.78,
    vlmMood: {
      summary: '포인트 컬러를 가진 그린 패브릭 소파베드',
      tags: ['모던', '그린', '패브릭'],
    },
    xaiReason: '소파 구조는 유사하나 색상과 공간 분위기 차이가 있습니다.',
    xaiResult: {
      criteria: [
        {
          label: '형태',
          score: 29,
          comment: '전체적인 소파베드 구조가 비슷합니다.',
        },
        {
          label: '색상',
          score: 8,
          comment: '객체의 브라운 색상과 차이가 큽니다.',
        },
      ],
      summary: '형태 유사도는 있으나 색상 조건이 달라 세 번째 후보입니다.',
    },
  },
];

export const DEMO_OBJECTS: FurnitureObject[] = [
  {
    bbox: [250, 45, 850, 950],
    candidates: DEMO_SKUS,
    category: '소파',
    confidence: 0.97,
    description: '이미지 중앙의 브라운 패브릭 2인 소파베드',
    id: 'demo-sofa-bed',
    metadata: {
      attributes: { color: '브라운', material: '패브릭', size: '2인용' },
      category: '소파',
      description: '낮은 팔걸이와 분할 쿠션이 있는 브라운 패브릭 소파베드',
      keyFeatures: ['패브릭', '브라운', '2인용', '소파베드'],
      subCategory: '소파베드',
    },
    name: '2인 소파베드',
    objectIdx: 0,
  },
];
