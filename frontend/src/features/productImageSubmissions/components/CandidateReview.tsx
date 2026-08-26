import { useMemo, useState } from 'react';
import { Check, ChevronRight, HelpCircle, Search } from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { ATTRIBUTE_LABELS } from '@/features/tagging/constants/skuAttributes';
import type { SkuCandidate } from '@/features/tagging/types';
import { buildSkuAttributeRows } from '@/features/tagging/utils/skuAttributes';
import { cn } from '@/lib/utils';

const VERDICT_LABELS = {
  MATCH: '일치',
  MISMATCH: '불일치',
  UNKNOWN: '판단 불가',
} as const;

const VERDICT_STYLES = {
  MATCH: 'bg-emerald-50 text-emerald-700',
  MISMATCH: 'bg-rose-50 text-rose-700',
  UNKNOWN: 'bg-amber-50 text-amber-700',
} as const;

type CandidateReviewProps = {
  candidates: SkuCandidate[];
  imageUrl: string;
  isBusy: boolean;
  onConfirm: (candidate: SkuCandidate) => void;
  onNoMatch: () => void;
  onOpenCatalogSearch: () => void;
};

/**
 * 업로드한 제품 이미지 1장을 분석해 얻은 SKU 후보 목록을 보여줍니다.
 * 연출 이미지 태깅의 RecommendationPanel과 같은 패턴(후보 카드 목록 +
 * 상세 비교 + XAI 요약)을 쓰되, 크롭이 아니라 이미지 전체가 곧 비교
 * 대상이라 객체 탐색·페이지 이동 없이 후보 1세트만 다룹니다.
 */
export const CandidateReview = ({
  candidates,
  imageUrl,
  isBusy,
  onConfirm,
  onNoMatch,
  onOpenCatalogSearch,
}: CandidateReviewProps) => {
  const [focusedSku, setFocusedSku] = useState(candidates[0]?.sku);
  const focusedCandidate = useMemo(
    () =>
      candidates.find((candidate) => candidate.sku === focusedSku) ??
      candidates[0],
    [candidates, focusedSku],
  );

  if (!focusedCandidate) return null;

  const metadataCriteria = (focusedCandidate.xaiResult?.criteria ?? []).filter(
    (criterion) => criterion.key,
  );
  const similarity = focusedCandidate.metadataScore ?? focusedCandidate.score;
  const attributeRows = buildSkuAttributeRows(focusedCandidate, null);

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-extrabold text-text-primary">
            AI 추천 후보
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            업로드한 이미지와 유사한 카탈로그 SKU {candidates.length}건을
            찾았습니다. 일치하는 상품이 있으면 확정하고, 없으면 신규 등록으로
            넘어가세요.
          </p>
        </div>
      </div>

      <div className="mt-5 grid overflow-hidden rounded-2xl border border-border bg-bg-primary xl:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-bg-tertiary/70 p-3 xl:border-b-0 xl:border-r">
          <div className="mb-3 rounded-xl border border-primary-200 bg-primary-20 p-3">
            <p className="text-xs font-bold text-primary-700">
              원하는 SKU가 후보에 없나요?
            </p>
            <Button
              className="mt-2.5"
              fullWidth
              onClick={onOpenCatalogSearch}
              size="md"
              startDecorator={<Search size={16} />}
              variant="primary-outlined"
            >
              전체 카탈로그 검색
            </Button>
          </div>
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
                    'min-w-[220px] rounded-xl border p-3 text-left transition-all xl:min-w-0',
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
                      {candidate.score !== null ? (
                        <span className="mt-2 flex items-center gap-2">
                          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-100">
                            <span
                              className="block h-full rounded-full bg-emerald-600"
                              style={{ width: `${candidate.score}%` }}
                            />
                          </span>
                          <span className="text-[11px] font-extrabold text-emerald-700">
                            {candidate.score}%
                          </span>
                        </span>
                      ) : null}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <article className="min-w-0 p-5 sm:p-6">
          <div className="flex flex-col gap-1 border-b border-neutral-100 pb-5">
            <h3 className="text-lg font-extrabold text-text-primary">
              {focusedCandidate.name}
            </h3>
            <p className="font-mono text-xs text-text-tertiary">
              {focusedCandidate.sku}
            </p>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(240px,0.85fr)]">
            <div className="rounded-xl bg-bg-tertiary/75 p-5">
              <div className="flex min-h-40 items-center justify-center gap-4 sm:gap-6">
                <div className="w-28 text-center sm:w-32">
                  <div className="flex h-28 items-center justify-center overflow-hidden rounded-lg border border-border bg-bg-primary">
                    <img
                      alt="업로드한 제품"
                      className="size-full object-contain p-2"
                      src={imageUrl}
                    />
                  </div>
                  <p className="mt-2 text-[11px] font-semibold text-text-secondary">
                    업로드한 이미지
                  </p>
                </div>
                <ChevronRight
                  className="shrink-0 text-text-quaternary"
                  size={20}
                />
                <div className="w-28 text-center sm:w-32">
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
              <p className="text-xs font-bold text-text-secondary">유사도</p>
              <div className="mt-3 flex items-end gap-2">
                <span className="text-4xl font-extrabold tracking-[-0.05em] text-blue-700">
                  {similarity === null ? '—' : `${similarity}%`}
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-4 text-text-tertiary">
                이미지 임베딩 유사도와 메타데이터 비교 결과를 종합한
                일치도입니다.
              </p>
            </div>
          </div>

          {metadataCriteria.length > 0 ? (
            <div className="mt-5">
              <p className="text-xs font-bold text-text-secondary">
                메타데이터 단위 검증
              </p>
              <div className="mt-2 overflow-x-auto rounded-xl border border-neutral-100">
                <table className="w-full min-w-[560px] text-left text-xs">
                  <thead className="bg-bg-tertiary text-text-tertiary">
                    <tr>
                      <th className="px-3 py-2 font-bold">메타데이터</th>
                      <th className="px-3 py-2 font-bold">SKU 카탈로그 값</th>
                      <th className="px-3 py-2 font-bold">판정</th>
                      <th className="px-3 py-2 font-bold">판단 근거</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100">
                    {metadataCriteria.map((criterion) => {
                      const key = criterion.key as string;
                      const verdict = criterion.verdict ?? 'UNKNOWN';
                      return (
                        <tr key={key}>
                          <td className="px-3 py-3 font-bold text-text-primary">
                            {ATTRIBUTE_LABELS[key] ?? key}
                          </td>
                          <td className="px-3 py-3 text-text-secondary">
                            {String(focusedCandidate.attrs[key] ?? '정보 없음')}
                          </td>
                          <td className="px-3 py-3">
                            <span
                              className={cn(
                                'rounded-full px-2 py-1 text-[11px] font-bold',
                                VERDICT_STYLES[verdict],
                              )}
                            >
                              {VERDICT_LABELS[verdict]}
                            </span>
                          </td>
                          <td className="px-3 py-3 leading-5 text-text-secondary">
                            {criterion.comment || '판단 근거가 없습니다.'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                  <p className="text-xs font-bold text-emerald-700">공통점</p>
                  <p className="mt-1 text-xs leading-5 text-emerald-900">
                    {focusedCandidate.xaiResult?.common ||
                      '확인된 공통점이 없습니다.'}
                  </p>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                  <p className="text-xs font-bold text-amber-700">
                    차이점 · 확인 필요
                  </p>
                  <p className="mt-1 text-xs leading-5 text-amber-900">
                    {focusedCandidate.xaiResult?.difference ||
                      '확인된 차이점이 없습니다.'}
                  </p>
                </div>
              </div>
            </div>
          ) : null}

          {metadataCriteria.length === 0 ? (
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
          ) : null}

          <div className="mt-6 flex flex-col-reverse gap-3 border-t border-neutral-100 pt-5 sm:flex-row sm:justify-between">
            <Button
              disabled={isBusy}
              onClick={onNoMatch}
              startDecorator={<HelpCircle size={16} />}
              variant="neutral-outlined"
            >
              일치하는 SKU 없음 · 신규 등록
            </Button>
            <Button
              disabled={isBusy}
              endDecorator={<Check size={16} />}
              onClick={() => onConfirm(focusedCandidate)}
            >
              이 SKU로 확정
            </Button>
          </div>
        </article>
      </div>
    </div>
  );
};
