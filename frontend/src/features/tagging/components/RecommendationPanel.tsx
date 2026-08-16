import { useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Search,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { ObjectCropPreview } from '@/features/tagging/components/ImagePreview';
import {
  ATTRIBUTE_LABELS,
  CATEGORY_ATTRIBUTE_FIELDS,
  COMMON_ATTRIBUTE_KEYS,
} from '@/features/tagging/constants/skuAttributes';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type { SkuCandidate } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

const rubricLabels = [
  ['구조', 30],
  ['색상', 30],
  ['디테일', 20],
  ['맥락', 20],
] as const;

const formatAttributeValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'null';
  if (typeof value === 'boolean') return value ? '있음' : '없음';
  return String(value);
};

const buildAttributeRows = (
  candidate: SkuCandidate,
  fallbackCategory: string | null,
): Array<[string, string]> => {
  const category = candidate.category ?? fallbackCategory;
  const attrs = candidate.attrs ?? {};
  const categoryKeys = category ? (CATEGORY_ATTRIBUTE_FIELDS[category] ?? []) : [];

  return [
    ['카테고리', category ?? '가구'],
    ...COMMON_ATTRIBUTE_KEYS.map(
      (key): [string, string] => [
        ATTRIBUTE_LABELS[key] ?? key,
        formatAttributeValue(attrs[key]),
      ],
    ),
    ...categoryKeys.map(
      (key): [string, string] => [
        ATTRIBUTE_LABELS[key] ?? key,
        formatAttributeValue(attrs[key]),
      ],
    ),
  ];
};

export const RecommendationPanel = () => {
  const { changeStage, selectSku, selectedObject, selectedSku, uploadedImage } =
    useTaggingWorkflow();
  const candidates = useMemo(
    () => selectedObject?.candidates ?? [],
    [selectedObject],
  );
  const [focusedSku, setFocusedSku] = useState(
    selectedSku?.sku ?? candidates[0]?.sku,
  );
  const focusedCandidate = useMemo(
    () =>
      candidates.find((candidate) => candidate.sku === focusedSku) ??
      candidates[0],
    [candidates, focusedSku],
  );

  if (!focusedCandidate) return null;

  const rubricScores: Array<number | null> = focusedCandidate.rubric
    ? [
        focusedCandidate.rubric.breakdown.structure,
        focusedCandidate.rubric.breakdown.color,
        focusedCandidate.rubric.breakdown.detail,
        focusedCandidate.rubric.breakdown.context,
      ]
    : [null, null, null, null];
  const isConfirmed = selectedSku?.sku === focusedCandidate.sku;
  // 소규모 배열 조합이라 useMemo 없이 매 렌더마다 계산해도 무방합니다.
  // (아래 return null 분기 뒤라 훅으로 두면 훅 규칙에 걸립니다.)
  const attributeRows = buildAttributeRows(
    focusedCandidate,
    selectedObject?.category ?? null,
  );

  return (
    <section>
      <div className="mb-4 flex flex-col gap-4 rounded-xl border border-border bg-bg-primary px-5 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-base font-extrabold text-neutral-800">
            유사 SKU 후보 · {selectedObject?.category ?? '선택 객체'}
          </p>
          <p className="mt-1 text-xs leading-5 text-neutral-500">
            객체 크롭 이미지의 임베딩 유사도와 루브릭 검증 결과입니다. 총{' '}
            {candidates.length}건
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-bg-tertiary px-3 py-2 text-xs font-bold text-text-secondary">
            객체 1 / 1
          </span>
          <Button
            onClick={() => changeStage('detect')}
            size="sm"
            variant="neutral-outlined"
          >
            객체 다시 선택
          </Button>
        </div>
      </div>

      <div className="grid overflow-hidden rounded-2xl border border-border bg-bg-primary shadow-[0_1px_3px_rgba(15,23,42,0.08)] xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-bg-tertiary/70 p-3 xl:border-b-0 xl:border-r">
          <p className="px-2 pb-2 text-xs font-bold text-text-secondary">
            후보 목록
          </p>
          <div className="flex gap-2 overflow-x-auto pb-1 xl:flex-col xl:overflow-visible">
            {candidates.map((candidate, index) => {
              const isFocused = focusedCandidate.sku === candidate.sku;
              return (
                <button
                  aria-pressed={isFocused}
                  className={cn(
                    'min-w-[245px] rounded-xl border p-3 text-left transition-all xl:min-w-0',
                    isFocused
                      ? 'border-blue-600 bg-white shadow-[0_0_0_1px_#2563eb]'
                      : 'border-border bg-white hover:border-blue-300',
                  )}
                  key={candidate.sku}
                  onClick={() => setFocusedSku(candidate.sku)}
                  type="button"
                >
                  <div className="flex items-start gap-3">
                    <FurnitureArtwork
                      className="h-14 w-14 shrink-0"
                      imageUrl={candidate.imageUrl}
                      kind={candidate.kind}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] font-bold text-text-tertiary">
                          {candidate.sku}
                        </span>
                        <span className="text-[10px] font-bold text-text-quaternary">
                          {index + 1}위
                        </span>
                      </span>
                      <span className="mt-1 block truncate text-xs font-extrabold text-text-primary">
                        {candidate.name}
                      </span>
                      <span className="mt-2 flex items-center gap-2">
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-100">
                          <span
                            className="block h-full rounded-full bg-emerald-600"
                            style={{ width: `${candidate.score ?? 0}%` }}
                          />
                        </span>
                        <span className="text-[11px] font-extrabold text-emerald-700">
                          {candidate.score === null
                            ? 'null'
                            : `${candidate.score}%`}
                        </span>
                      </span>
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
          <Button
            className="mt-3"
            fullWidth
            onClick={() => changeStage('catalog')}
            size="sm"
            startDecorator={<Search size={15} />}
            variant="neutral-outlined"
          >
            전체 카탈로그 검색
          </Button>
        </aside>

        <article className="min-w-0 p-5 sm:p-6">
          <div className="flex flex-col gap-4 border-b border-neutral-100 pb-5 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h2 className="text-lg font-extrabold text-text-primary">
                  {focusedCandidate.name}
                </h2>
                <span className="rounded-full bg-success-50 px-2 py-0.5 text-[11px] font-bold text-success-600">
                  추천
                </span>
              </div>
              <p className="mt-1 font-mono text-xs text-text-tertiary">
                {focusedCandidate.sku} · {focusedCandidate.size ?? 'null'}
              </p>
            </div>
            <div className="text-left sm:text-right">
              <p className="text-2xl font-extrabold tracking-[-0.04em] text-emerald-700">
                {focusedCandidate.score === null
                  ? 'null'
                  : `${focusedCandidate.score}%`}
              </p>
              <p className="text-[11px] font-semibold text-text-tertiary">
                최종 매칭 점수
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.92fr)]">
            <div className="rounded-xl bg-bg-tertiary/75 p-5">
              <div className="flex min-h-44 items-center justify-center gap-3 sm:gap-6">
                <div className="w-28 text-center sm:w-36">
                  <ObjectCropPreview
                    image={uploadedImage}
                    object={selectedObject}
                  />
                  <p className="mt-2 text-[11px] font-semibold text-text-secondary">
                    탐지 객체 크롭
                  </p>
                </div>
                <ChevronRight
                  className="shrink-0 text-text-quaternary"
                  size={20}
                />
                <div className="w-28 text-center sm:w-36">
                  <FurnitureArtwork
                    imageUrl={focusedCandidate.imageUrl}
                    kind={focusedCandidate.kind}
                  />
                  <p className="mt-2 text-[11px] font-semibold text-text-secondary">
                    SKU 대표 이미지
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-border p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold text-text-secondary">
                  VLM 루브릭 채점
                </p>
                <span className="text-sm font-extrabold text-text-primary">
                  {focusedCandidate.rubric?.totalScore ?? 'null'}
                  /100
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {rubricLabels.map(([label, maximum], index) => {
                  const value = rubricScores[index];
                  const percentage =
                    value === null ? 0 : (value / maximum) * 100;
                  return (
                    <div
                      className="grid grid-cols-[42px_minmax(0,1fr)_44px] items-center gap-2"
                      key={label}
                    >
                      <span className="text-xs font-semibold text-text-secondary">
                        {label}
                      </span>
                      <span className="h-1.5 overflow-hidden rounded-full bg-neutral-100">
                        <span
                          className="block h-full rounded-full bg-emerald-600"
                          style={{ width: `${percentage}%` }}
                        />
                      </span>
                      <span className="text-right text-xs font-bold text-emerald-700">
                        {value === null ? 'null' : `${value}/${maximum}`}
                      </span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 border-t border-neutral-100 pt-3 text-xs leading-5 text-text-secondary">
                {focusedCandidate.rubric?.xaiReason ??
                  focusedCandidate.xaiReason ??
                  'null'}
              </p>
            </div>
          </div>

          <div className="mt-5">
            <p className="text-xs font-bold text-text-secondary">
              SKU 카탈로그 속성
            </p>
            <dl className="mt-2 divide-y divide-neutral-100 border-y border-neutral-100">
              {attributeRows.map(([label, value]) => (
                <div
                  className="grid grid-cols-[92px_minmax(0,1fr)] gap-3 px-2 py-3"
                  key={label}
                >
                  <dt className="text-xs text-text-tertiary">{label}</dt>
                  <dd className="text-xs font-bold text-text-primary">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="mt-6 flex flex-col-reverse gap-3 border-t border-neutral-100 pt-5 sm:flex-row sm:justify-between">
            <Button
              onClick={() => changeStage('detect')}
              startDecorator={<ArrowLeft size={16} />}
              variant="neutral-outlined"
            >
              객체 다시 선택
            </Button>
            <div className="grid gap-3 sm:flex">
              <Button
                onClick={() => selectSku(focusedCandidate)}
                startDecorator={
                  isConfirmed ? <Check size={16} /> : <Sparkles size={16} />
                }
                variant={isConfirmed ? 'neutral-outlined' : 'primary-solid'}
              >
                {isConfirmed ? '선택됨' : '이 SKU 확정'}
              </Button>
              <Button
                disabled={!isConfirmed}
                endDecorator={<ArrowRight size={16} />}
                onClick={() => changeStage('review')}
              >
                검수로 이동
              </Button>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
};
