import { useEffect, useMemo, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Eye,
  ImageOff,
  X,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import {
  confirmApproval,
  getApprovalDetail,
  listApprovals,
  rejectApproval,
  type ApprovalDetail,
  type ApprovalListItem,
  type ApprovalStatus,
} from '@/features/approvals/api/approvals';
import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  ATTRIBUTE_LABELS,
  CATEGORY_ATTRIBUTE_FIELDS,
  COMMON_ATTRIBUTE_KEYS,
} from '@/features/tagging/constants/skuAttributes';
import { cn } from '@/lib/utils';

type MetadataVerdict = 'MATCH' | 'MISMATCH' | 'UNKNOWN';

type MetadataComparisonRow = {
  cropValue: string | null;
  key: string;
  skuValue: string | null;
  verdict: MetadataVerdict;
};

const asComparableText = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

/**
 * 업로드 이미지에서 추출한 속성(object.attrs)과 SKU 카탈로그 속성을
 * 코드로 직접 비교해 판정을 만듭니다. 두 값 다 있고 같으면 일치, 둘 다
 * 있는데 다르면 불일치, 어느 한쪽이라도 없으면 판단 불가입니다. AI가
 * 저장 시점에 내린 판정을 다시 불러오는 대신 항상 그 자리에서 계산하므로
 * 이미 저장된 기존 승인 요청에도 그대로 적용됩니다.
 */
const buildMetadataComparisonRows = (
  category: string | null,
  cropAttrs: Record<string, unknown>,
  skuAttrs: Record<string, unknown>,
): MetadataComparisonRow[] => {
  const categoryKeys = category
    ? (CATEGORY_ATTRIBUTE_FIELDS[category] ?? [])
    : [];
  const keys = [...new Set([...COMMON_ATTRIBUTE_KEYS, ...categoryKeys])];

  return keys.map((key) => {
    const cropValue = asComparableText(cropAttrs[key]);
    const skuValue = asComparableText(skuAttrs[key]);
    const verdict: MetadataVerdict =
      cropValue === null || skuValue === null
        ? 'UNKNOWN'
        : cropValue === skuValue
          ? 'MATCH'
          : 'MISMATCH';
    return { cropValue, key, skuValue, verdict };
  });
};

const statuses: Array<{ label: string; value: ApprovalStatus | 'ALL' }> = [
  { label: '승인 대기', value: 'PENDING' },
  { label: '승인 완료', value: 'ACTIVE' },
  { label: '반려', value: 'REJECTED' },
  { label: '전체', value: 'ALL' },
];

const XAI_VERDICT_LABELS = {
  MATCH: '일치',
  MISMATCH: '불일치',
  UNKNOWN: '판단 불가',
} as const;

const XAI_VERDICT_STYLES = {
  MATCH: 'bg-emerald-50 text-emerald-700',
  MISMATCH: 'bg-rose-50 text-rose-700',
  UNKNOWN: 'bg-amber-50 text-amber-700',
} as const;

const statusStyles: Record<ApprovalStatus, string> = {
  ACTIVE: 'bg-success-50 text-success-600',
  PENDING: 'bg-warning-50 text-warning-600',
  REJECTED: 'bg-danger-20 text-danger-600',
};

const statusLabels: Record<ApprovalStatus, string> = {
  ACTIVE: '승인 완료',
  PENDING: '승인 대기',
  REJECTED: '반려',
};

/** 접힌 목록 레일의 썸네일에 얹는 작은 상태 점 색상입니다. */
const statusDotStyles: Record<ApprovalStatus, string> = {
  ACTIVE: 'bg-success-600',
  PENDING: 'bg-yellow-400',
  REJECTED: 'bg-danger-600',
};

const formatDate = (value: string): string =>
  new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));

/** SKU 속성(color, material 등)을 key-value 카드 목록으로 보여줍니다. */
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
    <dl className="grid gap-2 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div className="rounded-lg bg-bg-tertiary px-3 py-2" key={key}>
          <dt className="text-xs font-semibold text-text-secondary">{key}</dt>
          <dd className="mt-1 text-sm font-medium text-text-primary">
            {typeof value === 'string' ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
};

export const ApprovalPage = () => {
  const { user } = useAuth();
  const [status, setStatus] = useState<ApprovalStatus | 'ALL'>('PENDING');
  const [items, setItems] = useState<ApprovalListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [detail, setDetail] = useState<ApprovalDetail>();
  const [error, setError] = useState<string>();
  const [isLoading, setIsLoading] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [isListExpanded, setIsListExpanded] = useState(false);
  const [previewCandidateSkuId, setPreviewCandidateSkuId] = useState<
    number | null
  >(null);

  const session = user?.session;
  const isSuperAdmin = user?.role === 'SUPER_ADMIN';
  const selectedItem = useMemo(
    () => items.find((item) => item.requestId === selectedId),
    [items, selectedId],
  );
  const previewCandidate = useMemo(
    () =>
      detail?.candidates.find(
        (candidate) => candidate.skuId === previewCandidateSkuId,
      ) ?? null,
    [detail, previewCandidateSkuId],
  );
  // 승인/반려는 처음 승인 요청으로 들어온 확정 SKU를 보고 있을 때만
  // 가능합니다. 후보를 미리 보는 동안(previewCandidate가 확정 SKU와
  // 다를 때)에는 실수로 다른 SKU를 승인하지 않도록 막습니다.
  const isViewingConfirmedSku =
    !previewCandidate || previewCandidate.skuId === detail?.sku.skuId;

  const activeSku = previewCandidate ?? detail?.sku;
  const activeSimilarityScore = previewCandidate
    ? previewCandidate.similarityScore
    : (detail?.similarityScore ?? null);
  const activeSimilarityPercent =
    activeSimilarityScore === null
      ? null
      : Math.round(activeSimilarityScore * 100);
  const metadataComparisonRows = useMemo(() => {
    if (!detail) return [];
    const source = previewCandidate ?? detail.sku;
    return buildMetadataComparisonRows(
      source.category ?? detail.object.category,
      detail.object.attrs,
      source.attributes,
    );
  }, [detail, previewCandidate]);


  const refresh = async () => {
    if (!session) return;
    setIsLoading(true);
    setError(undefined);
    try {
      const nextItems = await listApprovals(session, status);
      setItems(nextItems);
      setSelectedId((currentId) =>
        nextItems.some((item) => item.requestId === currentId)
          ? currentId
          : nextItems[0]?.requestId,
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '승인 요청 목록을 불러오지 못했습니다.',
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!session) return undefined;
    let isMounted = true;
    void listApprovals(session, status)
      .then((nextItems) => {
        if (!isMounted) return;
        setItems(nextItems);
        setSelectedId((currentId) =>
          nextItems.some((item) => item.requestId === currentId)
            ? currentId
            : nextItems[0]?.requestId,
        );
      })
      .catch((requestError: unknown) => {
        if (!isMounted) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : '승인 요청 목록을 불러오지 못했습니다.',
        );
      });
    return () => {
      isMounted = false;
    };
  }, [session, status]);

  useEffect(() => {
    if (!session || !selectedId) return undefined;
    let isMounted = true;
    void getApprovalDetail(session, selectedId)
      .then((nextDetail) => {
        if (!isMounted) return;
        setDetail(nextDetail);
        setPreviewCandidateSkuId(null);
      })
      .catch((requestError: unknown) => {
        if (!isMounted) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : '승인 요청 상세를 불러오지 못했습니다.',
        );
      });
    return () => {
      isMounted = false;
    };
  }, [selectedId, session]);

  const handleConfirm = async () => {
    if (!session || !detail) return;
    setIsLoading(true);
    try {
      await confirmApproval(session, detail.requestId);
      await refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '승인 처리에 실패했습니다.',
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleReject = async () => {
    if (!session || !detail || !rejectReason.trim()) return;
    setIsLoading(true);
    try {
      await rejectApproval(session, detail.requestId, rejectReason.trim());
      setIsRejecting(false);
      setRejectReason('');
      await refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '반려 처리에 실패했습니다.',
      );
    } finally {
      setIsLoading(false);
    }
  };

  if (!user || user.role === 'USER') {
    return (
      <div className="px-6 py-6">
        <section className="studio-surface flex min-h-80 flex-col items-center justify-center px-6 text-center">
          <Eye className="size-8 text-text-quaternary" />
          <h1 className="mt-4 text-xl font-bold text-text-primary">
            관리자 전용 메뉴입니다
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            승인 요청은 관리자 계정으로만 확인할 수 있습니다.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="px-6 py-6 pb-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ClipboardCheck className="size-6 text-blue-700" />
            <h1 className="text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
              승인 관리
            </h1>
          </div>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            태깅으로 선택된 SKU와 객체 이미지를 검토한 뒤 카탈로그 이미지로
            승인합니다.
          </p>
        </div>
        <span className="rounded-full bg-bg-muted px-3 py-1.5 text-xs font-bold text-text-secondary">
          {isSuperAdmin ? '승인·반려 가능' : '승인 목록 조회'}
        </span>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {statuses.map((item) => (
          <button
            aria-pressed={status === item.value}
            className={cn(
              'rounded-full border px-3.5 py-2 text-sm font-semibold transition-colors',
              status === item.value
                ? 'border-blue-700 bg-blue-700 text-white'
                : 'border-border bg-bg-primary text-text-secondary hover:border-blue-300 hover:bg-bg-hover',
            )}
            key={item.value}
            onClick={() => setStatus(item.value)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? (
        <p
          className="mt-5 rounded-xl border border-danger-200 bg-danger-20 px-4 py-3 text-sm font-semibold text-danger-600"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div
        className={cn(
          'mt-5 grid min-h-[580px] gap-5',
          isListExpanded
            ? 'xl:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.5fr)]'
            : 'xl:grid-cols-[88px_minmax(0,1fr)]',
        )}
      >
        <section
          className={cn(
            'studio-surface min-h-0',
            isListExpanded ? 'p-3' : 'p-2',
          )}
        >
          {isListExpanded ? (
            <>
              <div className="flex items-center justify-between px-2 pb-3 pt-1">
                <button
                  aria-expanded={isListExpanded}
                  className="flex items-center gap-1.5 text-sm font-extrabold text-text-primary"
                  onClick={() => setIsListExpanded(false)}
                  title="목록 옆으로 접기"
                  type="button"
                >
                  <ChevronLeft size={16} />
                  승인 요청
                </button>
                <span className="text-xs font-semibold text-text-tertiary">
                  {isLoading ? '불러오는 중' : `${items.length}건`}
                </span>
              </div>
              <div className="max-h-[650px] space-y-2 overflow-y-auto pr-1">
                {items.map((item) => (
                  <button
                    aria-pressed={selectedId === item.requestId}
                    className={cn(
                      'flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors',
                      selectedId === item.requestId
                        ? 'border-blue-600 bg-blue-50 shadow-[0_0_0_1px_#2563eb]'
                        : 'border-border bg-bg-primary hover:border-blue-300 hover:bg-bg-hover',
                    )}
                    key={item.requestId}
                    onClick={() => setSelectedId(item.requestId)}
                    type="button"
                  >
                    <span className="size-12 shrink-0 overflow-hidden rounded-lg bg-bg-tertiary">
                      {item.sceneImageUrl ? (
                        <img
                          alt={item.productName}
                          className="size-full object-cover"
                          src={item.sceneImageUrl}
                        />
                      ) : (
                        <span className="flex size-full items-center justify-center">
                          <ImageOff className="size-4 text-text-quaternary" />
                        </span>
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-2">
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-text-primary">
                            {item.productName}
                          </span>
                          <span className="mt-1 block font-mono text-[11px] text-text-tertiary">
                            {item.skuCode} · 객체 {item.objectIdx + 1}
                          </span>
                        </span>
                        <span
                          className={cn(
                            'shrink-0 rounded-full px-2 py-1 text-[11px] font-bold',
                            statusStyles[item.status],
                          )}
                        >
                          {statusLabels[item.status]}
                        </span>
                      </span>
                      <span className="mt-2 block text-xs text-text-secondary">
                        {item.category ?? '카테고리 미지정'} · {item.originName}
                      </span>
                      <span className="mt-1 block text-[11px] text-text-tertiary">
                        {formatDate(item.requestedAt)}
                      </span>
                    </span>
                  </button>
                ))}
                {!isLoading && items.length === 0 ? (
                  <div className="flex min-h-60 flex-col items-center justify-center px-5 text-center text-text-tertiary">
                    <ClipboardCheck className="size-7" />
                    <p className="mt-3 text-sm font-semibold">
                      해당 요청이 없습니다
                    </p>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <button
                aria-expanded={isListExpanded}
                className="flex flex-col items-center gap-1 rounded-lg px-1 py-1.5 text-text-secondary transition-colors hover:bg-bg-hover"
                onClick={() => setIsListExpanded(true)}
                title="승인 요청 목록 펼치기"
                type="button"
              >
                <ChevronRight size={16} />
                <span className="text-[11px] font-extrabold leading-tight text-text-primary">
                  승인 요청
                </span>
                <span className="text-[10px] font-semibold leading-tight text-text-tertiary">
                  {isLoading ? '...' : `${items.length}건`}
                </span>
              </button>
              <div className="max-h-[600px] w-full space-y-2 overflow-y-auto">
                {items.map((item) => (
                  <button
                    aria-label={`${item.productName} 선택`}
                    aria-pressed={selectedId === item.requestId}
                    className={cn(
                      'relative mx-auto block size-14 overflow-hidden rounded-lg border-2 transition-colors',
                      selectedId === item.requestId
                        ? 'border-blue-600'
                        : 'border-border hover:border-blue-300',
                    )}
                    key={item.requestId}
                    onClick={() => setSelectedId(item.requestId)}
                    title={`${item.productName} · ${statusLabels[item.status]}`}
                    type="button"
                  >
                    {item.sceneImageUrl ? (
                      <img
                        alt={item.productName}
                        className="size-full object-cover"
                        src={item.sceneImageUrl}
                      />
                    ) : (
                      <span className="flex size-full items-center justify-center bg-bg-tertiary">
                        <ImageOff className="size-4 text-text-quaternary" />
                      </span>
                    )}
                    <span
                      className={cn(
                        'absolute right-0.5 top-0.5 size-2 rounded-full ring-1 ring-white',
                        statusDotStyles[item.status],
                      )}
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="studio-surface p-5 sm:p-6">
          {detail &&
          selectedItem &&
          detail.requestId === selectedItem.requestId ? (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-5">
                <div>
                  <p className="text-xs font-bold text-text-tertiary">
                    승인 대상 SKU
                  </p>
                  <h2 className="mt-1 text-xl font-extrabold text-text-primary">
                    {detail.sku.productName}
                  </h2>
                  <p className="mt-1 font-mono text-xs text-text-tertiary">
                    {detail.sku.skuCode}
                  </p>
                </div>
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1.5 text-xs font-bold',
                    statusStyles[detail.status],
                  )}
                >
                  {statusLabels[detail.status]}
                </span>
              </div>

              <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_160px]">
                <div className="rounded-xl bg-bg-tertiary p-4">
                  <p className="text-xs font-bold text-text-secondary">
                    원본의 선택 객체
                  </p>
                  <div className="mt-3 flex min-h-52 items-center justify-center rounded-lg bg-bg-primary">
                    {detail.sceneImage.imageUrl ? (
                      <div className="relative inline-block">
                        <img
                          alt={detail.sceneImage.originName}
                          className="block max-h-72 max-w-full rounded-lg"
                          src={detail.sceneImage.imageUrl}
                        />
                        {detail.object.bbox ? (
                          <div
                            className="detection-box pointer-events-none"
                            style={{
                              height: `${Math.max(
                                1,
                                (detail.object.bbox.ymax -
                                  detail.object.bbox.ymin) /
                                  10,
                              )}%`,
                              left: `${detail.object.bbox.xmin / 10}%`,
                              top: `${detail.object.bbox.ymin / 10}%`,
                              width: `${Math.max(
                                1,
                                (detail.object.bbox.xmax -
                                  detail.object.bbox.xmin) /
                                  10,
                              )}%`,
                            }}
                          >
                            <span>
                              {detail.object.category ??
                                `객체 ${detail.object.objectIdx + 1}`}
                            </span>
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <ImageOff className="size-8 text-text-quaternary" />
                    )}
                  </div>
                  <p className="mt-3 text-xs font-semibold text-text-secondary">
                    {detail.object.category ?? '카테고리 미지정'} · 객체{' '}
                    {detail.object.objectIdx + 1}
                  </p>
                </div>

                <div className="rounded-xl border border-border bg-bg-secondary p-4">
                  <p className="text-xs font-bold text-text-secondary">
                    {isViewingConfirmedSku
                      ? '선택한 SKU'
                      : '미리보기 중인 후보 SKU'}
                  </p>
                  <div className="mt-3 flex items-center gap-4">
                    <div className="flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-bg-tertiary">
                      {activeSku?.imageUrl ? (
                        <img
                          alt={activeSku.productName}
                          className="size-full object-cover"
                          src={activeSku.imageUrl}
                        />
                      ) : (
                        <ImageOff className="size-6 text-text-quaternary" />
                      )}
                    </div>
                    <div>
                      <p className="font-mono text-xs font-bold text-text-tertiary">
                        {activeSku?.skuCode}
                      </p>
                      <h3 className="mt-1 text-base font-extrabold text-text-primary">
                        {activeSku?.productName}
                      </h3>
                      <p className="mt-1 text-sm text-text-secondary">
                        {[
                          activeSku?.brand,
                          [activeSku?.category, activeSku?.subCategory]
                            .filter(Boolean)
                            .join(' > '),
                        ]
                          .filter(Boolean)
                          .join(' · ') || '-'}
                      </p>
                      {activeSku?.price != null ? (
                        <p className="mt-1 text-sm font-semibold text-text-primary">
                          {activeSku.price.toLocaleString('ko-KR')}원
                        </p>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col items-center justify-center rounded-xl bg-bg-primary px-4 py-3 text-center lg:border lg:border-border">
                  <p className="text-[11px] font-bold text-text-tertiary">
                    유사도
                  </p>
                  <p className="mt-1 text-2xl font-extrabold text-blue-700">
                    {activeSimilarityPercent === null
                      ? '-'
                      : `${activeSimilarityPercent}%`}
                  </p>
                </div>
              </div>

              {detail.candidates.length > 0 ? (
                <div className="mt-5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-bold text-text-secondary">
                      추천 후보 SKU · 클릭하면 아래 비교표가 바뀝니다
                    </p>
                    {!isViewingConfirmedSku ? (
                      <button
                        className="text-xs font-bold text-blue-700 hover:underline"
                        onClick={() => setPreviewCandidateSkuId(null)}
                        type="button"
                      >
                        확정 SKU로 돌아가기
                      </button>
                    ) : null}
                  </div>
                  <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                    {detail.candidates.map((candidate) => {
                      const isConfirmed = candidate.skuId === detail.sku.skuId;
                      const isActive = previewCandidate
                        ? previewCandidate.skuId === candidate.skuId
                        : isConfirmed;
                      return (
                        <button
                          aria-pressed={isActive}
                          className={cn(
                            'relative flex w-32 shrink-0 flex-col items-center gap-1 rounded-lg border p-2 text-center transition-colors',
                            isConfirmed
                              ? 'border-success-200 bg-success-50'
                              : 'border-border bg-bg-primary hover:border-blue-300',
                            isActive &&
                              'border-blue-600 shadow-[0_0_0_1px_#2563eb]',
                          )}
                          key={candidate.skuId}
                          onClick={() =>
                            setPreviewCandidateSkuId(candidate.skuId)
                          }
                          type="button"
                        >
                          {isConfirmed ? (
                            <span className="absolute -right-1 -top-1 flex size-5 items-center justify-center rounded-full bg-success-600 text-white">
                              <Check size={12} />
                            </span>
                          ) : null}
                          <span className="flex size-16 items-center justify-center overflow-hidden rounded-md bg-bg-tertiary">
                            {candidate.imageUrl ? (
                              <img
                                alt={candidate.productName}
                                className="size-full object-cover"
                                src={candidate.imageUrl}
                              />
                            ) : (
                              <ImageOff className="size-4 text-text-quaternary" />
                            )}
                          </span>
                          <span className="text-[10px] font-bold text-text-quaternary">
                            {candidate.viaSearch
                              ? '검색 선택'
                              : `${candidate.matchRank}위`}
                          </span>
                          <span className="w-full truncate font-mono text-[10px] text-text-tertiary">
                            {candidate.skuCode}
                          </span>
                          <span className="w-full truncate text-xs font-semibold text-text-primary">
                            {candidate.productName}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {metadataComparisonRows.length > 0 ? (
                <div className="mt-5">
                  <p className="text-xs font-bold text-text-secondary">
                    메타데이터 비교
                  </p>
                  <div className="mt-2 overflow-x-auto rounded-xl border border-neutral-100">
                    <table className="w-full min-w-[640px] text-left text-xs">
                      <thead className="bg-bg-tertiary text-text-tertiary">
                        <tr>
                          <th className="px-3 py-2 font-bold">메타데이터</th>
                          <th className="px-3 py-2 font-bold">업로드 이미지</th>
                          <th className="px-3 py-2 font-bold">판정</th>
                          <th className="px-3 py-2 font-bold">선택한 SKU</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100">
                        {metadataComparisonRows.map((row) => (
                          <tr key={row.key}>
                            <td className="px-3 py-3 font-bold text-text-primary">
                              {ATTRIBUTE_LABELS[row.key] ?? row.key}
                            </td>
                            <td className="px-3 py-3 text-text-secondary">
                              {row.cropValue ?? '판단 불가'}
                            </td>
                            <td className="px-3 py-3">
                              <span
                                className={cn(
                                  'rounded-full px-2 py-1 text-[11px] font-bold',
                                  XAI_VERDICT_STYLES[row.verdict],
                                )}
                              >
                                {XAI_VERDICT_LABELS[row.verdict]}
                              </span>
                            </td>
                            <td className="px-3 py-3 text-text-secondary">
                              {row.skuValue ?? '정보 없음'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="mt-5 rounded-xl border border-border p-4">
                  <p className="text-xs font-bold text-text-secondary">
                    SKU 속성
                  </p>
                  <div className="mt-3">
                    <AttributeList attrs={detail.sku.attributes} />
                  </div>
                </div>
              )}

              <dl className="mt-5 divide-y divide-border rounded-xl border border-border">
                <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 px-4 py-3 text-sm">
                  <dt className="text-text-tertiary">요청자</dt>
                  <dd className="font-semibold text-text-primary">
                    {detail.requestedByName ?? '-'}
                  </dd>
                </div>
                <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 px-4 py-3 text-sm">
                  <dt className="text-text-tertiary">요청 일시</dt>
                  <dd className="font-semibold text-text-primary">
                    {formatDate(detail.requestedAt)}
                  </dd>
                </div>
                {detail.rejectReason ? (
                  <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 px-4 py-3 text-sm">
                    <dt className="text-text-tertiary">반려 사유</dt>
                    <dd className="text-danger-600">{detail.rejectReason}</dd>
                  </div>
                ) : null}
              </dl>

              {isSuperAdmin && detail.actions.canConfirm ? (
                <div className="mt-5 border-t border-border pt-5">
                  {isRejecting ? (
                    <div className="rounded-xl bg-danger-20 p-4">
                      <label
                        className="text-sm font-bold text-text-primary"
                        htmlFor="reject-reason"
                      >
                        반려 사유
                      </label>
                      <textarea
                        className="mt-2 min-h-24 w-full rounded-lg border border-danger-200 bg-bg-primary p-3 text-sm outline-none focus:border-danger-600"
                        id="reject-reason"
                        onChange={(event) =>
                          setRejectReason(event.target.value)
                        }
                        placeholder="반려 사유를 입력해 주세요."
                        value={rejectReason}
                      />
                      <div className="mt-3 flex justify-end gap-2">
                        <Button
                          onClick={() => setIsRejecting(false)}
                          size="sm"
                          variant="neutral-outlined"
                        >
                          취소
                        </Button>
                        <Button
                          disabled={
                            !rejectReason.trim() ||
                            isLoading ||
                            !isViewingConfirmedSku
                          }
                          onClick={() => void handleReject()}
                          size="sm"
                        >
                          반려 확정
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                      <Button
                        disabled={isLoading || !isViewingConfirmedSku}
                        onClick={() => setIsRejecting(true)}
                        startDecorator={<X size={16} />}
                        variant="neutral-outlined"
                      >
                        반려
                      </Button>
                      <Button
                        disabled={isLoading || !isViewingConfirmedSku}
                        onClick={() => void handleConfirm()}
                        startDecorator={<Check size={16} />}
                      >
                        승인하고 SKU 이미지 등록
                      </Button>
                    </div>
                  )}
                </div>
              ) : null}
            </>
          ) : (
            <div className="flex min-h-[500px] flex-col items-center justify-center text-center text-text-tertiary">
              <ClipboardCheck className="size-9" />
              <p className="mt-3 text-sm font-semibold">
                왼쪽에서 승인 요청을 선택해 주세요
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
