import { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  Clock3,
  ImageOff,
  Tag,
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { Button } from '@/commons/components/Button';
import {
  APPROVAL_STATUS_LABELS,
  APPROVAL_STATUS_STYLES,
} from '@/features/approvals/constants/approvalStatus';
import { fetchTaggingHistoryDetail } from '@/features/tagging/api/tagging';
import type {
  HistoryBoundingBox,
  TaggingHistoryDetail,
} from '@/features/tagging/types';
import { cn } from '@/lib/utils';

const formatDateTime = (value: string): string => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('ko-KR', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date);
};

const AttributeList = ({ attrs }: { attrs: Record<string, unknown> }) => {
  const entries = Object.entries(attrs).filter(
    ([, value]) => value != null && value !== '',
  );
  if (entries.length === 0) {
    return (
      <p className="text-sm text-text-secondary">저장된 속성이 없습니다.</p>
    );
  }

  return (
    <dl className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
      {entries.map(([key, value]) => (
        <div className="rounded-lg bg-neutral-50 px-3 py-2" key={key}>
          <dt className="text-xs font-semibold text-text-secondary">{key}</dt>
          <dd className="mt-1 text-sm font-medium text-text-primary">
            {typeof value === 'string' ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
};

/** 탐지 결과는 이미지 크기와 무관한 0~1000 정규화 좌표입니다. */
const BoundingBox = ({ bbox }: { bbox: HistoryBoundingBox }) => (
  <span
    aria-label="탐지 객체 영역"
    className="pointer-events-none absolute border-2 border-primary bg-primary/10"
    style={{
      height: `${(bbox.ymax - bbox.ymin) / 10}%`,
      left: `${bbox.xmin / 10}%`,
      top: `${bbox.ymin / 10}%`,
      width: `${(bbox.xmax - bbox.xmin) / 10}%`,
    }}
  />
);

export const HistoryDetailPage = () => {
  const { resultId } = useParams<{ resultId: string }>();
  const [detail, setDetail] = useState<TaggingHistoryDetail>();
  const [error, setError] = useState<string>();
  const [isLoading, setIsLoading] = useState(true);
  const [isXaiExpanded, setIsXaiExpanded] = useState(false);

  const isValidResultId = Boolean(resultId && /^\d+$/.test(resultId));
  const loadDetail = useCallback(async (): Promise<void> => {
    if (!resultId || !/^\d+$/.test(resultId)) {
      setError('유효하지 않은 태깅 결과입니다.');
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(undefined);
    try {
      setDetail(await fetchTaggingHistoryDetail(resultId));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '태깅 결과를 불러오지 못했습니다.',
      );
    } finally {
      setIsLoading(false);
    }
  }, [resultId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  return (
    <div className="px-6 py-6 pb-10">
      <div>
        <Link
          className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
          to="/history"
        >
          <ArrowLeft size={16} /> 목록으로 돌아가기
        </Link>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-text-secondary">태깅 이력</p>
            <h1 className="studio-page-title text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
              태깅 결과 상세
            </h1>
          </div>
          {detail?.approvalStatus ? (
            <span
              className={cn(
                'rounded-full px-3 py-1 text-sm font-bold',
                APPROVAL_STATUS_STYLES[detail.approvalStatus],
              )}
            >
              {APPROVAL_STATUS_LABELS[detail.approvalStatus]}
            </span>
          ) : null}
        </div>

        {isLoading ? (
          <section className="studio-surface mt-6 flex min-h-60 items-center justify-center px-6 text-sm font-semibold text-text-secondary">
            결과를 불러오는 중입니다.
          </section>
        ) : null}
        {error ? (
          <section
            className="mt-6 rounded-md border border-warning-200 bg-warning-50 px-4 py-4 text-sm font-semibold text-warning-700"
            role="alert"
          >
            <p>{error}</p>
            <p className="mt-1 font-normal">
              결과가 존재하지 않거나 조회 권한이 없을 수 있습니다.
            </p>
            {isValidResultId ? (
              <Button
                className="mt-3"
                onClick={() => void loadDetail()}
                size="sm"
              >
                다시 시도
              </Button>
            ) : null}
          </section>
        ) : null}
        {detail && !isLoading ? (
          <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(520px,0.85fr)_minmax(0,1.15fr)]">
            <section className="studio-surface self-start p-5">
              <h2 className="text-base font-extrabold text-text-primary">
                연출 이미지와 탐지 객체
              </h2>
              {detail.sceneImage.imageUrl ? (
                <div className="mt-4 inline-block max-w-full overflow-hidden rounded-lg bg-neutral-100">
                  <div className="relative">
                    <img
                      alt={detail.sceneImage.imageName}
                      className="block max-h-[620px] max-w-full object-contain"
                      src={detail.sceneImage.imageUrl}
                    />
                    {detail.detectedObject.bbox ? (
                      <BoundingBox bbox={detail.detectedObject.bbox} />
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="mt-4 flex min-h-64 items-center justify-center rounded-lg bg-neutral-100 text-sm text-text-secondary">
                  <ImageOff className="mr-2" size={18} />
                  연출 이미지를 불러올 수 없습니다.
                </div>
              )}
              <p className="mt-3 text-sm text-text-secondary">
                {detail.sceneImage.imageName}
              </p>
            </section>

            <div className="space-y-6">
              <section className="studio-surface p-5">
                <h2 className="text-base font-extrabold text-text-primary">
                  탐지 객체
                </h2>
                <p className="mt-2 text-sm text-text-secondary">
                  {[
                    detail.detectedObject.category,
                    detail.detectedObject.subCategory,
                  ]
                    .filter(Boolean)
                    .join(' · ') || '분류 정보 없음'}
                </p>
                <h3 className="mt-5 text-sm font-bold text-text-primary">
                  추출 속성
                </h3>
                <div className="mt-2">
                  <AttributeList attrs={detail.detectedObject.attrs} />
                </div>
                {detail.detectedObject.vlmMood ? (
                  <div className="mt-5">
                    <h3 className="text-sm font-bold text-text-primary">
                      분위기 태그
                    </h3>
                    <p className="mt-2 text-sm text-text-secondary">
                      {detail.detectedObject.vlmMood.summary}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {detail.detectedObject.vlmMood.tags.map((tag) => (
                        <span
                          className="inline-flex items-center gap-1 rounded-full bg-primary-20 px-2.5 py-1 text-xs font-bold text-primary-700"
                          key={tag}
                        >
                          <Tag size={12} />
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="studio-surface p-5">
                <h2 className="text-base font-extrabold text-text-primary">
                  확정 SKU
                </h2>
                <div className="mt-4 flex gap-4">
                  {detail.matchedSku.imageUrl ? (
                    <img
                      alt={detail.matchedSku.productName}
                      className="size-24 rounded-lg border border-neutral-200 object-cover"
                      src={detail.matchedSku.imageUrl}
                    />
                  ) : (
                    <div className="flex size-24 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-text-secondary">
                      <ImageOff size={20} />
                    </div>
                  )}
                  <div>
                    <p className="font-mono text-xs font-bold text-primary">
                      {detail.matchedSku.sku}
                    </p>
                    <h3 className="mt-1 font-bold text-text-primary">
                      {detail.matchedSku.productName}
                    </h3>
                    <p className="mt-1 text-sm text-text-secondary">
                      {[
                        detail.matchedSku.brand,
                        detail.matchedSku.category,
                        detail.matchedSku.subCategory,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                    {detail.matchedSku.price !== null ? (
                      <p className="mt-1 text-sm font-semibold text-text-primary">
                        {detail.matchedSku.price.toLocaleString()}원
                      </p>
                    ) : null}
                  </div>
                </div>
                <h3 className="mt-5 text-sm font-bold text-text-primary">
                  SKU 속성
                </h3>
                <div className="mt-2">
                  <AttributeList attrs={detail.matchedSku.attrs} />
                </div>
              </section>

              <section className="studio-surface p-5">
                <h2 className="text-base font-extrabold text-text-primary">
                  판단 근거
                </h2>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-text-secondary">유사도</dt>
                    <dd className="mt-1 text-lg font-bold text-text-primary">
                      {detail.similarityScore === null
                        ? '-'
                        : `${detail.similarityScore}점`}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-text-secondary">생성 일시</dt>
                    <dd className="mt-1 flex items-center gap-1 font-medium text-text-primary">
                      <Clock3 size={14} />
                      {formatDateTime(detail.createdAt)}
                    </dd>
                  </div>
                </dl>
                {detail.xaiResult ? (
                  <div className="mt-5 border-t border-neutral-200 pt-4">
                    <button
                      aria-expanded={isXaiExpanded}
                      className="flex w-full items-center justify-between text-left text-sm font-bold text-text-primary"
                      onClick={() => setIsXaiExpanded((expanded) => !expanded)}
                      type="button"
                    >
                      XAI 판단 근거
                      {isXaiExpanded ? (
                        <ChevronUp size={16} />
                      ) : (
                        <ChevronDown size={16} />
                      )}
                    </button>
                    {isXaiExpanded ? (
                      <div className="mt-3">
                        <p className="text-sm text-text-secondary">
                          {detail.xaiResult.summary}
                        </p>
                        <div className="mt-3 space-y-2">
                          {detail.xaiResult.criteria.map((criterion, index) => (
                            <div
                              className="rounded-lg bg-neutral-50 px-3 py-2"
                              key={`${criterion.label}-${index}`}
                            >
                              <p className="text-sm font-bold text-text-primary">
                                {criterion.label} · {criterion.score}점
                              </p>
                              <p className="mt-1 text-xs text-text-secondary">
                                {criterion.comment}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="mt-5 border-t border-neutral-200 pt-4 text-sm text-text-secondary">
                    저장된 XAI 판단 근거가 없습니다.
                  </p>
                )}
              </section>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
