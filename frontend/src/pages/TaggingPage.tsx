import type React from 'react';
import { ChevronRight } from 'lucide-react';

import { CatalogPanel } from '@/features/tagging/components/CatalogPanel';
import { DetectionPanel } from '@/features/tagging/components/DetectionPanel';
import { RecommendationPanel } from '@/features/tagging/components/RecommendationPanel';
import { ReviewPanel } from '@/features/tagging/components/ReviewPanel';
import { UploadPanel } from '@/features/tagging/components/UploadPanel';
import {
  NoDetectionPanel,
  FailedPanel,
  LoadingPanel,
  SavedPanel,
} from '@/features/tagging/components/WorkflowStatus';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';

const PAGE_COPY = {
  upload: {
    eyebrow: '새 태깅 작업',
    title: '연출 이미지에서, 정확한 상품까지',
    description:
      '가구가 포함된 연출 이미지를 업로드하면 AI가 객체를 찾고 SKU 후보를 추천합니다.',
  },
  detect: {
    eyebrow: '객체 선택',
    title: 'AI가 찾은 가구를 확인해 주세요',
    description:
      '이미지 또는 오른쪽 목록에서 태깅할 가구 하나를 선택할 수 있습니다.',
  },
  'not-found': {
    eyebrow: '미탐지 보완',
    title: '가구를 자동으로 찾지 못했어요',
    description:
      '찾으려는 가구를 구체적으로 설명하면 이미지와 함께 한 번 더 분석합니다.',
  },
  recommend: {
    eyebrow: 'SKU 추천',
    title: '유사한 SKU를 추천했어요',
    description: '추천 근거를 비교한 뒤 가장 적합한 상품 하나를 선택해 주세요.',
  },
  catalog: {
    eyebrow: '카탈로그 검색',
    title: '전체 카탈로그에서 찾아볼까요?',
    description:
      'SKU 코드 또는 상품명으로 검색해 직접 상품을 선택할 수 있습니다.',
  },
  review: {
    eyebrow: '태깅 검수',
    title: '최종 태깅 정보를 검수해 주세요',
    description:
      '원본 이미지, 선택 객체, SKU 정보와 AI 태그를 확인한 후 저장합니다.',
  },
  saved: {
    eyebrow: '저장 완료',
    title: '상품 연결과 태그 저장을 완료했어요',
    description: '저장한 결과는 검수 이력에서 다시 확인할 수 있습니다.',
  },
  failed: {
    eyebrow: '미탐지 종료',
    title: '가구를 찾지 못했어요',
    description:
      '입력한 설명으로도 가구 객체를 확인하지 못했습니다. 다른 이미지를 업로드해 주세요.',
  },
} as const;

const getCopyKey = (stage: string): keyof typeof PAGE_COPY => {
  if (stage === 'analyzing') return 'upload';
  if (stage === 'redetecting') return 'not-found';
  if (stage === 'recommending') return 'recommend';
  if (stage === 'saving') return 'review';
  return stage as keyof typeof PAGE_COPY;
};

export const TaggingPage: React.FC = () => {
  const { analysisMode, analysisScenario, setAnalysisScenario, stage } =
    useTaggingWorkflow();
  const copy = PAGE_COPY[getCopyKey(stage)];

  return (
    <div className="px-6 py-6 pb-10">
      <div className="mb-6 flex items-start justify-between gap-6">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
              가구 태깅
            </span>
            <ChevronRight className="size-5 text-text-secondary" />
            <h1 className="studio-page-title text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
              {copy.eyebrow}
            </h1>
          </div>
          <p className="max-w-3xl pl-0 text-sm leading-6 text-text-secondary sm:pl-1">
            {copy.description}
          </p>
          {analysisMode ? (
            <span className="mt-2 inline-flex w-fit rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-700">
              {analysisMode === 'live'
                ? 'Gemini 실시간 분석 결과'
                : '객체 · SKU 선택 데모'}
            </span>
          ) : null}
        </div>
        {import.meta.env.DEV ? (
          <label className="hidden shrink-0 text-xs font-bold text-text-tertiary 2xl:block">
            UAT 시나리오
            <select
              className="ml-2 h-8 rounded-md border border-border bg-bg-primary px-2 text-xs font-medium text-text-secondary outline-none focus:border-blue-400"
              onChange={(event) =>
                setAnalysisScenario(
                  event.target.value === 'not-detected'
                    ? 'not-detected'
                    : 'detected',
                )
              }
              value={analysisScenario}
            >
              <option value="detected">정상 탐지</option>
              <option value="not-detected">미탐지</option>
            </select>
          </label>
        ) : null}
      </div>
      {stage === 'upload' ? <UploadPanel /> : null}
      {stage === 'analyzing' ? (
        <LoadingPanel
          description="이미지 품질과 가구 영역을 확인하고 있습니다."
          label="가구를 분석하고 있습니다"
        />
      ) : null}
      {stage === 'detect' ? <DetectionPanel /> : null}
      {stage === 'not-found' ? <NoDetectionPanel /> : null}
      {stage === 'redetecting' ? (
        <LoadingPanel
          description="입력한 설명과 이미지를 함께 분석하고 있습니다."
          label="가구를 다시 찾고 있습니다"
        />
      ) : null}
      {stage === 'recommending' ? (
        <LoadingPanel
          description="수정한 객체를 저장하고 각 객체의 SKU 후보를 조회하고 있습니다."
          label="유사 SKU를 찾고 있습니다"
        />
      ) : null}
      {stage === 'recommend' ? <RecommendationPanel /> : null}
      {stage === 'catalog' ? <CatalogPanel /> : null}
      {stage === 'review' ? <ReviewPanel /> : null}
      {stage === 'saving' ? (
        <LoadingPanel
          description="객체와 SKU 연결, 태그와 검수 이력을 기록하고 있습니다."
          label="태깅 결과를 저장하고 있습니다"
        />
      ) : null}
      {stage === 'saved' ? <SavedPanel /> : null}
      {stage === 'failed' ? <FailedPanel /> : null}
    </div>
  );
};
