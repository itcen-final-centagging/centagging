import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FileImage,
  ImagePlus,
  ImageUp,
  LoaderCircle,
  PackagePlus,
  Send,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  approveProductImageSubmission,
  configureProductImageSubmission,
  getProductImageSubmission,
  getProductImageSubmissionJob,
  listProductImageSubmissions,
  rejectProductImageSubmission,
  submitProductImageSubmission,
  uploadProductImageDrafts,
  type ProductImageSubmission,
  type ProductImageSubmissionCandidateSku,
  type ProductImageSubmissionDraft,
  type ProductImageSubmissionJobResult,
  type ProductImageSubmissionJobStatus,
  type ProductImageSubmissionStatus,
  type ProductImageType,
} from '@/features/productImageSubmissions/api/productImageSubmissions';
import { CandidateReview } from '@/features/productImageSubmissions/components/CandidateReview';
import { SkuCatalogSearchDialog } from '@/features/productImageSubmissions/components/SkuCatalogSearchDialog';
import {
  toCandidateFromDetail,
  type SkuDetail,
} from '@/features/tagging/api/tagging';
import {
  CATEGORIES,
  getAllowedValues,
  getCategoryAttributeKeys,
  getSubCategories,
  withCurrentValue,
} from '@/features/tagging/constants/catalogSpec';
import {
  ATTRIBUTE_LABELS,
  CATEGORY_ATTRIBUTE_FIELDS,
  COMMON_ATTRIBUTE_KEYS,
} from '@/features/tagging/constants/skuAttributes';
import type { SkuCandidate } from '@/features/tagging/types';
import { buildSkuAttributeRows } from '@/features/tagging/utils/skuAttributes';
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
 * 업로드 이미지에서 추출한 속성(proposedAttributes)과 연결한 SKU 속성을
 * 코드로 직접 비교해 판정을 만듭니다. 승인 관리 페이지(ApprovalPage)의
 * buildMetadataComparisonRows와 같은 규칙을 씁니다.
 */
const buildMetadataComparisonRows = (
  category: string | null,
  uploadedAttrs: Record<string, unknown>,
  skuAttrs: Record<string, unknown>,
): MetadataComparisonRow[] => {
  const categoryKeys = category
    ? (CATEGORY_ATTRIBUTE_FIELDS[category] ?? [])
    : [];
  const keys = [...new Set([...COMMON_ATTRIBUTE_KEYS, ...categoryKeys])];

  return keys.map((key) => {
    const cropValue = asComparableText(uploadedAttrs[key]);
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

const statusDotStyles: Record<ProductImageSubmissionStatus, string> = {
  APPROVED: 'bg-success-600',
  DRAFT: 'bg-neutral-400',
  PENDING: 'bg-yellow-400',
  REJECTED: 'bg-danger-600',
};

const JOB_POLL_INTERVAL_MS = 1000;
const JOB_POLL_TIMEOUT_MS = 600_000;

const sleep = async (milliseconds: number): Promise<void> =>
  new Promise((resolve) => {
    globalThis.setTimeout(resolve, milliseconds);
  });

type SubmissionJobState = {
  errorMessage: string | null;
  result: ProductImageSubmissionJobResult | null;
  status: ProductImageSubmissionJobStatus;
};

const statuses: Array<{
  label: string;
  value: ProductImageSubmissionStatus | 'ALL';
}> = [
  { label: '작성 중', value: 'DRAFT' },
  { label: '승인 대기', value: 'PENDING' },
  { label: '승인 완료', value: 'APPROVED' },
  { label: '반려', value: 'REJECTED' },
  { label: '전체', value: 'ALL' },
];

const statusLabel: Record<ProductImageSubmissionStatus, string> = {
  APPROVED: '승인 완료',
  DRAFT: '작성 중',
  PENDING: '승인 대기',
  REJECTED: '반려',
};

const statusStyle: Record<ProductImageSubmissionStatus, string> = {
  APPROVED: 'bg-success-50 text-success-600',
  DRAFT: 'bg-bg-muted text-text-secondary',
  PENDING: 'bg-warning-50 text-warning-600',
  REJECTED: 'bg-danger-20 text-danger-600',
};

const fieldClassName =
  'mt-1.5 min-h-10 w-full rounded-lg border border-border bg-bg-primary px-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-quaternary focus:border-blue-500';
const fieldLabelClassName = 'text-xs font-bold text-text-secondary';

const emptyDraft = (): ProductImageSubmissionDraft => ({
  imageType: 'ANGLE',
  proposedAttributes: {},
  proposedBrand: null,
  proposedCategory: null,
  proposedPrice: null,
  proposedProductName: null,
  proposedSkuCode: null,
  proposedSubCategory: null,
  targetSkuCode: null,
  targetType: 'NEW',
});

const draftFromSubmission = (
  submission: ProductImageSubmission,
): ProductImageSubmissionDraft => {
  const targetType = submission.targetType ?? 'NEW';
  return {
    imageType:
      targetType === 'EXISTING' && submission.imageType === 'MAIN'
        ? 'ANGLE'
        : submission.imageType,
    proposedAttributes: submission.proposedAttributes,
    proposedBrand: submission.proposedBrand,
    proposedCategory: submission.proposedCategory,
    proposedPrice: submission.proposedPrice,
    proposedProductName: submission.proposedProductName,
    proposedSkuCode: submission.proposedSkuCode,
    proposedSubCategory: submission.proposedSubCategory,
    targetSkuCode: submission.targetSkuCode,
    targetType,
  };
};

const formatDate = (value: string | null): string => {
  if (!value) return '-';
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
};

const formatPrice = (price: number | null): string =>
  price === null ? '가격 미입력' : `${price.toLocaleString('ko-KR')}원`;

const SubmissionBadge = ({
  status,
}: Pick<ProductImageSubmission, 'status'>) => (
  <span
    className={cn(
      'inline-flex rounded-full px-2.5 py-1 text-[11px] font-extrabold',
      statusStyle[status],
    )}
  >
    {statusLabel[status]}
  </span>
);

const SubmissionMeta = ({
  submission,
}: {
  submission: ProductImageSubmission;
}) => {
  const title =
    submission.targetProductName ??
    submission.proposedProductName ??
    '상품 정보 작성 필요';
  const code = submission.targetSkuCode ?? submission.proposedSkuCode;

  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-bold text-text-primary">{title}</p>
      <p className="mt-1 truncate font-mono text-[11px] text-text-tertiary">
        {code ?? 'SKU 미지정'}
      </p>
    </div>
  );
};

export const ProductImageRegistrationPage = () => {
  const { user } = useAuth();
  const session = user?.session;
  const isSuperAdmin = user?.role === 'SUPER_ADMIN';
  const [status, setStatus] = useState<ProductImageSubmissionStatus | 'ALL'>(
    'DRAFT',
  );
  const [items, setItems] = useState<ProductImageSubmission[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [detail, setDetail] = useState<ProductImageSubmission>();
  const [draft, setDraft] = useState<ProductImageSubmissionDraft>(emptyDraft);
  const [error, setError] = useState<string>();
  const [isBusy, setIsBusy] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [jobStates, setJobStates] = useState<
    Record<number, SubmissionJobState>
  >({});
  const [resolvedCandidateIds, setResolvedCandidateIds] = useState<Set<number>>(
    new Set(),
  );
  const [confirmedTarget, setConfirmedTarget] = useState<SkuCandidate>();
  const [isCatalogSearchOpen, setIsCatalogSearchOpen] = useState(false);
  const [isListExpanded, setIsListExpanded] = useState(false);
  const [previewCandidateSkuId, setPreviewCandidateSkuId] = useState<
    number | null
  >(null);
  const selectedIdRef = useRef<number | undefined>(undefined);
  const startedPollsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const refresh = useCallback(async () => {
    if (!session) return;
    setIsBusy(true);
    setError(undefined);
    try {
      const nextItems = await listProductImageSubmissions(session, status);
      setItems(nextItems);
      setSelectedId((currentId) =>
        nextItems.some((item) => item.submissionId === currentId)
          ? currentId
          : nextItems[0]?.submissionId,
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '제품 이미지 등록 목록을 불러오지 못했습니다.',
      );
    } finally {
      setIsBusy(false);
    }
  }, [session, status]);

  useEffect(() => {
    const refreshTimer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(refreshTimer);
  }, [refresh]);

  useEffect(() => {
    if (!session || !selectedId) return undefined;
    let isMounted = true;
    void getProductImageSubmission(session, selectedId)
      .then((nextDetail) => {
        if (!isMounted) return;
        setDetail(nextDetail);
        setDraft(draftFromSubmission(nextDetail));
        setConfirmedTarget(undefined);
        setIsRejecting(false);
        setRejectReason('');
        setPreviewCandidateSkuId(null);
      })
      .catch((requestError: unknown) => {
        if (!isMounted) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : '제품 이미지 등록 상세를 불러오지 못했습니다.',
        );
      });
    return () => {
      isMounted = false;
    };
  }, [selectedId, session]);

  const replaceItem = useCallback((nextDetail: ProductImageSubmission) => {
    setDetail(nextDetail);
    setDraft(draftFromSubmission(nextDetail));
    setItems((currentItems) =>
      currentItems.map((item) =>
        item.submissionId === nextDetail.submissionId ? nextDetail : item,
      ),
    );
  }, []);

  const pollSubmissionJob = useCallback(
    async (targetSession: string, submissionId: number, jobId: string) => {
      if (startedPollsRef.current.has(submissionId)) return;
      startedPollsRef.current.add(submissionId);

      setJobStates((current) => ({
        ...current,
        [submissionId]: { errorMessage: null, result: null, status: 'PENDING' },
      }));

      const timeoutAt = Date.now() + JOB_POLL_TIMEOUT_MS;
      let finalState: SubmissionJobState = {
        errorMessage: '분석 시간이 초과되었습니다.',
        result: null,
        status: 'FAILED',
      };

      while (Date.now() < timeoutAt) {
        try {
          const job = await getProductImageSubmissionJob(targetSession, jobId);
          if (job.status === 'SUCCEEDED' || job.status === 'FAILED') {
            finalState = {
              errorMessage: job.errorMessage,
              result: job.result,
              status: job.status,
            };
            break;
          }
          setJobStates((current) => ({
            ...current,
            [submissionId]: {
              errorMessage: null,
              result: null,
              status: job.status,
            },
          }));
        } catch {
          // 네트워크 오류 등은 다음 폴링 주기에 다시 시도합니다.
        }
        await sleep(JOB_POLL_INTERVAL_MS);
      }

      setJobStates((current) => ({ ...current, [submissionId]: finalState }));

      if (selectedIdRef.current === submissionId) {
        try {
          const refreshed = await getProductImageSubmission(
            targetSession,
            submissionId,
          );
          replaceItem(refreshed);
        } catch {
          // 상세 새로고침 실패는 무시합니다 — 목록에서 다시 선택하면 재조회됩니다.
        }
      }
    },
    [replaceItem],
  );

  useEffect(() => {
    if (
      !session ||
      !detail ||
      !detail.jobId ||
      detail.status !== 'DRAFT' ||
      detail.targetType
    ) {
      return;
    }
    const jobId = detail.jobId;
    const submissionId = detail.submissionId;

    void Promise.resolve().then(() =>
      pollSubmissionJob(session, submissionId, jobId),
    );
  }, [detail, session, pollSubmissionJob]);

  /**
   * 후보(AI 추천 또는 카탈로그 검색)를 확정하면 별도 확인 화면 없이 바로
   * 기존 SKU 연결로 저장하고 승인 대기열로 제출합니다. 태깅작업과 달리
   * 이미지 유형을 고를 필요가 없어(기본값 ANGLE) 검수 단계를 하나 줄인
   * 흐름입니다.
   */
  const handleCandidateConfirm = async (candidate: SkuCandidate) => {
    if (!session || !detail) return;
    const jobResult = jobStates[detail.submissionId]?.result;
    const nextDraft: ProductImageSubmissionDraft = {
      ...draft,
      imageType: 'ANGLE',
      proposedAttributes:
        jobResult?.proposedAttributes ?? draft.proposedAttributes,
      proposedCategory: jobResult?.proposedCategory ?? draft.proposedCategory,
      proposedSubCategory:
        jobResult?.proposedSubCategory ?? draft.proposedSubCategory,
      targetSkuCode: candidate.sku,
      targetType: 'EXISTING',
    };
    setDraft(nextDraft);
    setIsBusy(true);
    setError(undefined);
    try {
      const savedDetail = await configureProductImageSubmission(
        session,
        detail.submissionId,
        nextDraft,
      );
      const submittedDetail = await submitProductImageSubmission(
        session,
        savedDetail.submissionId,
      );
      replaceItem(submittedDetail);
      setStatus('PENDING');
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '승인 요청을 제출하지 못했습니다.',
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleNoMatchingCandidate = () => {
    if (!detail) return;
    setDraft((current) => ({
      ...current,
      imageType: 'MAIN',
      targetType: 'NEW',
    }));
    setResolvedCandidateIds((current) =>
      new Set(current).add(detail.submissionId),
    );
  };

  const handleCatalogSearchSelect = (skuDetail: SkuDetail) => {
    if (!detail) return;
    const submissionId = detail.submissionId;
    const searchedCandidate = toCandidateFromDetail(skuDetail);
    setJobStates((current) => {
      const existing = current[submissionId];
      const existingCandidates = existing?.result?.skuCandidates ?? [];
      if (existingCandidates.some((c) => c.sku === searchedCandidate.sku)) {
        return current;
      }
      return {
        ...current,
        [submissionId]: {
          errorMessage: existing?.errorMessage ?? null,
          result: {
            proposedAttributes: existing?.result?.proposedAttributes ?? {},
            proposedCategory: existing?.result?.proposedCategory ?? null,
            proposedSubCategory: existing?.result?.proposedSubCategory ?? null,
            skuCandidates: [searchedCandidate, ...existingCandidates],
          },
          status: 'SUCCEEDED',
        },
      };
    });
    setIsCatalogSearchOpen(false);
  };

  const handleBackToCandidates = () => {
    if (!detail) return;
    setResolvedCandidateIds((current) => {
      const next = new Set(current);
      next.delete(detail.submissionId);
      return next;
    });
  };

  const saveDraft = async (): Promise<ProductImageSubmission | undefined> => {
    if (!session || !detail) return undefined;
    if (draft.targetType === 'EXISTING' && !draft.targetSkuCode) {
      setError('연결할 기존 SKU를 선택해 주세요.');
      return undefined;
    }
    if (
      draft.targetType === 'NEW' &&
      (!draft.proposedSkuCode?.trim() || !draft.proposedProductName?.trim())
    ) {
      setError('신규 SKU 코드와 상품명은 필수입니다.');
      return undefined;
    }
    setIsBusy(true);
    setError(undefined);
    try {
      const nextDetail = await configureProductImageSubmission(
        session,
        detail.submissionId,
        draft,
      );
      replaceItem(nextDetail);
      return nextDetail;
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '등록 정보를 저장하지 못했습니다.',
      );
      return undefined;
    } finally {
      setIsBusy(false);
    }
  };

  const handleSubmit = async () => {
    const savedDetail = await saveDraft();
    if (!session || !savedDetail) return;
    setIsBusy(true);
    try {
      const nextDetail = await submitProductImageSubmission(
        session,
        savedDetail.submissionId,
      );
      replaceItem(nextDetail);
      setStatus('PENDING');
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '승인 요청을 제출하지 못했습니다.',
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleFiles = async (files: File[]) => {
    if (!session || files.length === 0) return;
    setIsBusy(true);
    setError(undefined);
    try {
      const created = await uploadProductImageDrafts(session, files);
      setStatus('DRAFT');
      setItems(created);
      setSelectedId(created[0]?.submissionId);
      setDetail(created[0]);
      if (created[0]) setDraft(draftFromSubmission(created[0]));
      created.forEach((item) => {
        if (item.jobId) {
          void pollSubmissionJob(session, item.submissionId, item.jobId);
        }
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '제품 이미지를 업로드하지 못했습니다.',
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleApprove = async () => {
    if (!session || !detail) return;
    setIsBusy(true);
    setError(undefined);
    try {
      const nextDetail = await approveProductImageSubmission(
        session,
        detail.submissionId,
      );
      replaceItem(nextDetail);
      await refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '승인 처리에 실패했습니다.',
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleReject = async () => {
    if (!session || !detail || !rejectReason.trim()) return;
    setIsBusy(true);
    setError(undefined);
    try {
      const nextDetail = await rejectProductImageSubmission(
        session,
        detail.submissionId,
        rejectReason.trim(),
      );
      replaceItem(nextDetail);
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
      setIsBusy(false);
    }
  };

  const jobState = detail ? jobStates[detail.submissionId] : undefined;
  const isCandidateResolved = detail
    ? resolvedCandidateIds.has(detail.submissionId)
    : false;
  const candidateAwaitingDecision =
    !!detail &&
    detail.status === 'DRAFT' &&
    !detail.targetType &&
    !isCandidateResolved;
  const jobCandidates = jobState?.result?.skuCandidates ?? [];
  const isAnalyzing =
    candidateAwaitingDecision &&
    (jobState?.status === 'PENDING' || jobState?.status === 'RUNNING');
  const shouldShowCandidates =
    candidateAwaitingDecision &&
    jobState?.status === 'SUCCEEDED' &&
    jobCandidates.length > 0;
  const isExistingTarget =
    !!detail &&
    detail.status === 'DRAFT' &&
    !isAnalyzing &&
    !shouldShowCandidates &&
    draft.targetType === 'EXISTING';
  const showSidePanel =
    !!detail &&
    (detail.status !== 'DRAFT' ||
      (!isAnalyzing && !shouldShowCandidates && !isExistingTarget));

  return (
    <div className="px-6 py-6 pb-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <PackagePlus className="size-6 text-blue-700" />
            <h1 className="text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
              제품 이미지 등록
            </h1>
          </div>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            여러 제품 이미지를 올린 뒤, 각각 기존 SKU에 연결하거나 신규 상품으로
            등록해 최종 승인을 요청합니다.
          </p>
        </div>
        <label className="inline-flex min-h-[42px] cursor-pointer items-center justify-center gap-2 rounded-xl border border-blue-700 bg-blue-700 px-[18px] text-sm font-semibold text-white shadow-[0_1px_2px_rgba(15,23,42,0.12)] transition-all hover:-translate-y-px hover:bg-blue-900">
          <ImagePlus className="size-4" />
          제품 이미지 업로드
          <input
            accept="image/jpeg,image/png"
            className="sr-only"
            disabled={isBusy}
            multiple
            onChange={(event) => {
              void handleFiles(Array.from(event.currentTarget.files ?? []));
              event.currentTarget.value = '';
            }}
            type="file"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-tertiary">
        <span className="rounded-md bg-bg-muted px-2 py-1 font-semibold">
          JPG, PNG · 파일당 최대 10MB
        </span>
        <span>한 번에 최대 20장 · 이미지별로 개별 처리</span>
        {isSuperAdmin ? (
          <span className="rounded-md bg-blue-100 px-2 py-1 font-semibold text-blue-800">
            전체 요청 승인·반려 가능
          </span>
        ) : null}
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
          className="mt-5 flex items-center gap-2 rounded-xl border border-danger-200 bg-danger-20 px-4 py-3 text-sm font-semibold text-danger-600"
          role="alert"
        >
          <CircleAlert className="size-4 shrink-0" />
          {error}
        </p>
      ) : null}

      <div
        className={cn(
          'mt-5 grid min-h-[620px] gap-5',
          isListExpanded
            ? 'xl:grid-cols-[minmax(295px,0.7fr)_minmax(0,1.5fr)]'
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
                  등록/승인 관리
                </button>
                <span className="text-xs font-semibold text-text-tertiary">
                  {isBusy ? '처리 중' : `${items.length}건`}
                </span>
              </div>
              {items.length === 0 && !isBusy ? (
                <div className="flex min-h-56 flex-col items-center justify-center px-5 text-center">
                  <ImageUp className="size-8 text-text-quaternary" />
                  <p className="mt-3 text-sm font-bold text-text-primary">
                    표시할 등록 요청이 없습니다
                  </p>
                  <p className="mt-1 text-xs leading-5 text-text-secondary">
                    제품 이미지를 업로드하면 이곳에서 하나씩 등록 정보를 입력할
                    수 있습니다.
                  </p>
                </div>
              ) : null}
              <div className="max-h-[650px] space-y-2 overflow-y-auto pr-1">
                {items.map((item) => (
                  <button
                    aria-pressed={selectedId === item.submissionId}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors',
                      selectedId === item.submissionId
                        ? 'border-blue-600 bg-blue-50 shadow-[0_0_0_1px_#2563eb]'
                        : 'border-border bg-bg-primary hover:border-blue-300 hover:bg-bg-hover',
                    )}
                    key={item.submissionId}
                    onClick={() => setSelectedId(item.submissionId)}
                    type="button"
                  >
                    <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-bg-tertiary">
                      <img
                        alt="업로드한 제품"
                        className="h-full w-full object-cover"
                        src={item.imageUrl}
                      />
                    </div>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <SubmissionBadge status={item.status} />
                        <span className="text-[11px] text-text-quaternary">
                          #{item.submissionId}
                        </span>
                      </span>
                      <span className="mt-2 block">
                        <SubmissionMeta submission={item} />
                      </span>
                    </span>
                    <ChevronRight className="size-4 shrink-0 text-text-quaternary" />
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <button
                aria-expanded={isListExpanded}
                className="flex flex-col items-center gap-1 rounded-lg px-1 py-1.5 text-text-secondary transition-colors hover:bg-bg-hover"
                onClick={() => setIsListExpanded(true)}
                title="등록/승인 목록 펼치기"
                type="button"
              >
                <ChevronRight size={16} />
                <span className="text-[11px] font-extrabold leading-tight text-text-primary">
                  등록 목록
                </span>
                <span className="text-[10px] font-semibold leading-tight text-text-tertiary">
                  {isBusy ? '...' : `${items.length}건`}
                </span>
              </button>
              <div className="max-h-[600px] w-full space-y-2 overflow-y-auto">
                {items.map((item) => (
                  <button
                    aria-label={`요청 #${item.submissionId} 선택`}
                    aria-pressed={selectedId === item.submissionId}
                    className={cn(
                      'relative mx-auto block size-14 overflow-hidden rounded-lg border-2 transition-colors',
                      selectedId === item.submissionId
                        ? 'border-blue-600'
                        : 'border-border hover:border-blue-300',
                    )}
                    key={item.submissionId}
                    onClick={() => setSelectedId(item.submissionId)}
                    title={`#${item.submissionId} · ${statusLabel[item.status]}`}
                    type="button"
                  >
                    <img
                      alt="업로드한 제품"
                      className="size-full object-cover"
                      src={item.imageUrl}
                    />
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

        <section className="studio-surface min-h-0 overflow-hidden">
          {!detail || !selectedId ? (
            <div className="flex min-h-[580px] flex-col items-center justify-center px-6 text-center">
              {isBusy ? (
                <LoaderCircle className="size-7 animate-spin text-blue-700" />
              ) : (
                <FileImage className="size-8 text-text-quaternary" />
              )}
              <h2 className="mt-4 text-lg font-bold text-text-primary">
                등록할 제품 이미지를 선택하세요
              </h2>
              <p className="mt-2 text-sm text-text-secondary">
                선택한 이미지의 SKU 연결 방식과 상품 메타데이터를 확인할 수
                있습니다.
              </p>
            </div>
          ) : (
            <div
              className={cn(
                'grid min-h-[620px]',
                showSidePanel &&
                  'lg:grid-cols-[minmax(230px,0.75fr)_minmax(0,1.25fr)]',
              )}
            >
              {showSidePanel ? (
                <div className="border-b border-border bg-bg-secondary p-5 lg:border-b-0 lg:border-r">
                  <div className="flex items-center justify-between gap-3">
                    <SubmissionBadge status={detail.status} />
                    <span className="font-mono text-[11px] font-bold text-text-tertiary">
                      REQUEST #{detail.submissionId}
                    </span>
                  </div>
                  <div className="mt-4 flex min-h-60 items-center justify-center overflow-hidden rounded-xl border border-border bg-bg-primary p-3">
                    <img
                      alt="등록할 제품"
                      className="max-h-72 w-full object-contain"
                      src={detail.imageUrl}
                    />
                  </div>
                  <dl className="mt-5 space-y-3 text-xs">
                    <div className="flex justify-between gap-4">
                      <dt className="text-text-tertiary">등록 요청자</dt>
                      <dd className="font-bold text-text-secondary">
                        {detail.requestedByName}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-text-tertiary">업로드 일시</dt>
                      <dd className="text-right font-medium text-text-secondary">
                        {formatDate(detail.requestedAt)}
                      </dd>
                    </div>
                    {detail.submittedAt ? (
                      <div className="flex justify-between gap-4">
                        <dt className="text-text-tertiary">제출 일시</dt>
                        <dd className="text-right font-medium text-text-secondary">
                          {formatDate(detail.submittedAt)}
                        </dd>
                      </div>
                    ) : null}
                    {detail.reviewedAt ? (
                      <div className="flex justify-between gap-4">
                        <dt className="text-text-tertiary">최종 검토</dt>
                        <dd className="text-right font-medium text-text-secondary">
                          {detail.reviewedByName} ·{' '}
                          {formatDate(detail.reviewedAt)}
                        </dd>
                      </div>
                    ) : null}
                  </dl>
                </div>
              ) : null}

              <div className="p-5">
                {isAnalyzing ? (
                  <div className="flex min-h-[420px] flex-col items-center justify-center px-6 text-center">
                    <LoaderCircle className="size-8 animate-spin text-blue-700" />
                    <h2 className="mt-4 text-lg font-bold text-text-primary">
                      이미지를 분석하고 있습니다
                    </h2>
                    <p className="mt-2 max-w-sm text-sm text-text-secondary">
                      카테고리·속성을 추출하고 유사한 SKU를 찾는 중입니다.
                      완료되면 자동으로 추천 후보가 표시됩니다.
                    </p>
                  </div>
                ) : shouldShowCandidates ? (
                  <CandidateReview
                    candidates={jobCandidates}
                    imageUrl={detail.imageUrl}
                    isBusy={isBusy}
                    key={jobCandidates[0]?.sku ?? 'empty'}
                    onConfirm={handleCandidateConfirm}
                    onNoMatch={handleNoMatchingCandidate}
                    onOpenCatalogSearch={() => setIsCatalogSearchOpen(true)}
                  />
                ) : isExistingTarget ? (
                  <ExistingTargetConfirm
                    confirmedTarget={confirmedTarget}
                    draft={draft}
                    hasCandidates={jobCandidates.length > 0}
                    isBusy={isBusy}
                    onBackToCandidates={handleBackToCandidates}
                    onChange={setDraft}
                    onOpenCatalogSearch={() => setIsCatalogSearchOpen(true)}
                    onSave={() => {
                      void saveDraft();
                    }}
                    onSubmit={() => {
                      void handleSubmit();
                    }}
                  />
                ) : detail.status === 'DRAFT' ? (
                  <>
                    {jobState?.status === 'FAILED' ? (
                      <p className="mb-4 flex items-center gap-2 rounded-xl border border-danger-200 bg-danger-20 px-4 py-3 text-sm font-semibold text-danger-600">
                        <CircleAlert className="size-4 shrink-0" />
                        자동 분석에 실패했습니다. SKU 정보를 직접 입력해 주세요.
                      </p>
                    ) : null}
                    <NewProductForm
                      draft={draft}
                      isBusy={isBusy}
                      onChange={setDraft}
                      onSave={() => {
                        void saveDraft();
                      }}
                      onSubmit={() => {
                        void handleSubmit();
                      }}
                    />
                  </>
                ) : (
                  <SubmissionReview
                    detail={detail}
                    isBusy={isBusy}
                    isRejecting={isRejecting}
                    isSuperAdmin={isSuperAdmin}
                    onApprove={() => {
                      void handleApprove();
                    }}
                    onPreviewCandidateChange={setPreviewCandidateSkuId}
                    onReject={() => {
                      void handleReject();
                    }}
                    onRejectingChange={setIsRejecting}
                    onRejectReasonChange={setRejectReason}
                    previewCandidateSkuId={previewCandidateSkuId}
                    rejectReason={rejectReason}
                  />
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      {isCatalogSearchOpen ? (
        <SkuCatalogSearchDialog
          onClose={() => setIsCatalogSearchOpen(false)}
          onSelect={handleCatalogSearchSelect}
        />
      ) : null}
    </div>
  );
};

type ExistingTargetConfirmProps = {
  confirmedTarget?: SkuCandidate;
  draft: ProductImageSubmissionDraft;
  hasCandidates: boolean;
  isBusy: boolean;
  onBackToCandidates: () => void;
  onChange: (draft: ProductImageSubmissionDraft) => void;
  onOpenCatalogSearch: () => void;
  onSave: () => void;
  onSubmit: () => void;
};

const ExistingTargetConfirm = ({
  confirmedTarget,
  draft,
  hasCandidates,
  isBusy,
  onBackToCandidates,
  onChange,
  onOpenCatalogSearch,
  onSave,
  onSubmit,
}: ExistingTargetConfirmProps) => {
  const setField = <Key extends keyof ProductImageSubmissionDraft>(
    field: Key,
    value: ProductImageSubmissionDraft[Key],
  ) => onChange({ ...draft, [field]: value });

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-extrabold text-text-primary">
            선택한 SKU에 이미지 추가
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            이미지 유형을 정한 뒤 승인 요청을 보냅니다.
          </p>
        </div>
        <select
          aria-label="이미지 유형"
          className="min-h-9 rounded-lg border border-border bg-bg-primary px-2 text-xs font-semibold text-text-secondary"
          onChange={(event) =>
            setField('imageType', event.target.value as ProductImageType)
          }
          value={draft.imageType}
        >
          <option value="ANGLE">각도 이미지</option>
          <option value="DETAIL">상세 이미지</option>
          <option value="STYLING">연출 이미지</option>
        </select>
      </div>

      <div className="mt-5 flex items-center gap-3 rounded-xl border border-border bg-bg-secondary p-3">
        <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-bg-tertiary">
          {confirmedTarget?.imageUrl ? (
            <img
              alt="선택한 SKU 대표 이미지"
              className="h-full w-full object-cover"
              src={confirmedTarget.imageUrl}
            />
          ) : (
            <FileImage className="size-5 text-text-quaternary" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-bold text-text-primary">
            {confirmedTarget?.name ?? '선택한 SKU'}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-text-tertiary">
            {confirmedTarget?.sku ?? draft.targetSkuCode}
          </p>
        </div>
      </div>

      {confirmedTarget ? (
        <div className="mt-5">
          <p className="text-xs font-bold text-text-secondary">
            선택한 SKU 카탈로그 속성
          </p>
          <p className="mt-1 text-xs text-text-tertiary">
            등록 전 마지막으로 카테고리·속성이 맞는지 한 번 더 확인해 주세요.
          </p>
          <dl className="mt-2 divide-y divide-neutral-100 border-y border-neutral-100">
            {buildSkuAttributeRows(confirmedTarget, null).map(
              ([label, value]) => (
                <div
                  className="grid grid-cols-[92px_minmax(0,1fr)] gap-3 px-2 py-3"
                  key={label}
                >
                  <dt className="text-xs text-text-tertiary">{label}</dt>
                  <dd className="text-xs font-bold text-text-primary">
                    {value}
                  </dd>
                </div>
              ),
            )}
          </dl>

          {(confirmedTarget.styleTags?.length ?? 0) > 0 ||
          (confirmedTarget.spaceMoods?.length ?? 0) > 0 ? (
            <div className="mt-3 rounded-xl bg-bg-secondary p-4">
              <p className="text-xs font-bold text-text-tertiary">
                공간 분위기 · 스타일 태그
              </p>
              {confirmedTarget.styleTags &&
              confirmedTarget.styleTags.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {confirmedTarget.styleTags.map((tag) => (
                    <span
                      className="rounded-full bg-primary-20 px-2.5 py-1 text-xs font-bold text-primary-700"
                      key={tag}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
              {confirmedTarget.spaceMoods &&
              confirmedTarget.spaceMoods.length > 0 ? (
                <ul className="mt-2 space-y-1">
                  {confirmedTarget.spaceMoods.map((mood) => (
                    <li className="text-sm text-text-primary" key={mood}>
                      &ldquo;{mood}&rdquo;
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {hasCandidates ? (
          <button
            className="text-xs font-bold text-blue-700 hover:underline"
            onClick={onBackToCandidates}
            type="button"
          >
            AI 추천 후보 다시 보기
          </button>
        ) : null}
        <button
          className="text-xs font-bold text-blue-700 hover:underline"
          onClick={onOpenCatalogSearch}
          type="button"
        >
          다른 SKU 검색
        </button>
      </div>

      <div className="mt-8 flex flex-wrap justify-end gap-2 border-t border-border pt-5">
        <Button disabled={isBusy} onClick={onSave} variant="neutral-outlined">
          임시 저장
        </Button>
        <Button
          disabled={isBusy}
          endDecorator={<Send className="size-4" />}
          onClick={onSubmit}
        >
          승인 요청 제출
        </Button>
      </div>
    </div>
  );
};

type NewProductFormProps = {
  draft: ProductImageSubmissionDraft;
  isBusy: boolean;
  onChange: (draft: ProductImageSubmissionDraft) => void;
  onSave: () => void;
  onSubmit: () => void;
};

const NewProductForm = ({
  draft,
  isBusy,
  onChange,
  onSave,
  onSubmit,
}: NewProductFormProps) => {
  const setField = <Key extends keyof ProductImageSubmissionDraft>(
    field: Key,
    value: ProductImageSubmissionDraft[Key],
  ) => onChange({ ...draft, [field]: value });

  const handleCategoryChange = (nextCategory: string) => {
    onChange({
      ...draft,
      proposedAttributes: {},
      proposedCategory: nextCategory || null,
      proposedSubCategory: null,
    });
  };

  const handleAttributeChange = (key: string, value: string) => {
    const nextAttributes = { ...draft.proposedAttributes };
    if (value) {
      nextAttributes[key] = value;
    } else {
      delete nextAttributes[key];
    }
    onChange({ ...draft, proposedAttributes: nextAttributes });
  };

  const attributeKeys = [
    ...COMMON_ATTRIBUTE_KEYS,
    ...getCategoryAttributeKeys(draft.proposedCategory),
  ];

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-extrabold text-text-primary">
            신규 상품 등록 정보
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            자동으로 추출된 카테고리·속성을 검토하고 필요하면 수정한 뒤 승인
            요청을 보냅니다.
          </p>
        </div>
        <span className="inline-flex min-h-9 items-center rounded-lg border border-border bg-bg-muted px-3 text-xs font-semibold text-text-secondary">
          대표 이미지
        </span>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field
          label="신규 SKU 코드"
          onChange={(value) => setField('proposedSkuCode', value || null)}
          placeholder="예: CHR-2042"
          value={draft.proposedSkuCode ?? ''}
        />
        <Field
          label="상품명"
          onChange={(value) => setField('proposedProductName', value || null)}
          placeholder="예: 우드 다이닝 체어"
          value={draft.proposedProductName ?? ''}
        />
        <Field
          label="브랜드"
          onChange={(value) => setField('proposedBrand', value || null)}
          placeholder="브랜드명"
          value={draft.proposedBrand ?? ''}
        />
        <div>
          <label className={fieldLabelClassName} htmlFor="product-price">
            가격
          </label>
          <input
            className={fieldClassName}
            id="product-price"
            min="0"
            onChange={(event) =>
              setField(
                'proposedPrice',
                event.target.value ? Number(event.target.value) : null,
              )
            }
            placeholder="원 단위"
            type="number"
            value={draft.proposedPrice ?? ''}
          />
        </div>
      </div>

      <p className="mt-5 text-[11px] font-bold text-text-tertiary">
        AI 추출 정보
      </p>
      <div className="mt-2 grid gap-4 sm:grid-cols-2">
        <div>
          <label className={fieldLabelClassName} htmlFor="product-category">
            대분류
          </label>
          <select
            className={fieldClassName}
            id="product-category"
            onChange={(event) => handleCategoryChange(event.target.value)}
            value={draft.proposedCategory ?? ''}
          >
            <option value="">대분류를 선택하세요</option>
            {withCurrentValue(CATEGORIES, draft.proposedCategory).map(
              (category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ),
            )}
          </select>
        </div>
        <div>
          <label className={fieldLabelClassName} htmlFor="product-sub-category">
            소분류
          </label>
          <select
            className={cn(
              fieldClassName,
              'disabled:bg-bg-muted disabled:text-text-quaternary',
            )}
            disabled={!draft.proposedCategory}
            id="product-sub-category"
            onChange={(event) =>
              setField('proposedSubCategory', event.target.value || null)
            }
            value={draft.proposedSubCategory ?? ''}
          >
            <option value="">소분류를 선택하세요</option>
            {withCurrentValue(
              getSubCategories(draft.proposedCategory),
              draft.proposedSubCategory,
            ).map((subCategory) => (
              <option key={subCategory} value={subCategory}>
                {subCategory}
              </option>
            ))}
          </select>
        </div>
      </div>

      {draft.proposedCategory ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {attributeKeys.map((key) => {
            const currentValue = draft.proposedAttributes[key];
            const fieldId = `product-attribute-${key}`;
            return (
              <div key={key}>
                <label className={fieldLabelClassName} htmlFor={fieldId}>
                  {ATTRIBUTE_LABELS[key] ?? key}
                </label>
                <select
                  className={fieldClassName}
                  id={fieldId}
                  onChange={(event) =>
                    handleAttributeChange(key, event.target.value)
                  }
                  value={typeof currentValue === 'string' ? currentValue : ''}
                >
                  <option value="">선택 안 함</option>
                  {withCurrentValue(
                    getAllowedValues(draft.proposedCategory, key),
                    typeof currentValue === 'string' ? currentValue : undefined,
                  ).map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="mt-8 flex flex-wrap justify-end gap-2 border-t border-border pt-5">
        <Button disabled={isBusy} onClick={onSave} variant="neutral-outlined">
          임시 저장
        </Button>
        <Button
          disabled={isBusy}
          endDecorator={<Send className="size-4" />}
          onClick={onSubmit}
        >
          승인 요청 제출
        </Button>
      </div>
    </div>
  );
};

const Field = ({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) => (
  <div>
    <label className={fieldLabelClassName}>
      {label}
      <input
        className={fieldClassName}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  </div>
);

type SubmissionReviewProps = {
  detail: ProductImageSubmission;
  isBusy: boolean;
  isRejecting: boolean;
  isSuperAdmin: boolean;
  onApprove: () => void;
  onPreviewCandidateChange: (skuId: number | null) => void;
  onReject: () => void;
  onRejectingChange: (isRejecting: boolean) => void;
  onRejectReasonChange: (rejectReason: string) => void;
  previewCandidateSkuId: number | null;
  rejectReason: string;
};

const SubmissionReview = ({
  detail,
  isBusy,
  isRejecting,
  isSuperAdmin,
  onApprove,
  onPreviewCandidateChange,
  onReject,
  onRejectingChange,
  onRejectReasonChange,
  previewCandidateSkuId,
  rejectReason,
}: SubmissionReviewProps) => {
  const isExisting = detail.targetType === 'EXISTING';
  const title =
    detail.targetProductName ?? detail.proposedProductName ?? '상품 정보 없음';
  const code = detail.targetSkuCode ?? detail.proposedSkuCode ?? 'SKU 미지정';

  const confirmedCandidate =
    detail.candidates.find(
      (candidate) => candidate.skuCode === detail.targetSkuCode,
    ) ?? null;
  const fallbackCandidate: ProductImageSubmissionCandidateSku | null =
    isExisting && detail.targetSkuCode
      ? {
          attributes: detail.targetAttributes,
          brand: detail.targetBrand,
          category: detail.targetCategory,
          imageUrl: detail.targetMainImageUrl,
          matchRank: 0,
          price: detail.targetPrice,
          productName: detail.targetProductName ?? detail.targetSkuCode,
          similarityScore: null,
          skuCode: detail.targetSkuCode,
          skuId: 0,
          subCategory: detail.targetSubCategory,
          viaSearch: true,
          xaiCommon: '',
          xaiDifference: '',
        }
      : null;
  const previewCandidate =
    detail.candidates.find(
      (candidate) => candidate.skuId === previewCandidateSkuId,
    ) ?? null;
  const activeCandidate =
    previewCandidate ?? confirmedCandidate ?? fallbackCandidate;

  const isViewingConfirmedTarget =
    !previewCandidate || previewCandidate.skuCode === detail.targetSkuCode;
  const activeSimilarityPercent =
    activeCandidate?.similarityScore == null
      ? null
      : Math.round(activeCandidate.similarityScore * 100);
  const metadataComparisonRows =
    isExisting && activeCandidate
      ? buildMetadataComparisonRows(
          activeCandidate.category ?? detail.proposedCategory,
          detail.proposedAttributes,
          activeCandidate.attributes,
        )
      : [];

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-extrabold text-text-primary">{title}</h2>
          <p className="mt-1 font-mono text-xs font-bold text-text-tertiary">
            {code}
          </p>
        </div>
        <SubmissionBadge status={detail.status} />
      </div>

      {isExisting ? (
        <>
          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_160px]">
            <div className="rounded-xl bg-bg-tertiary p-4">
              <p className="text-xs font-bold text-text-secondary">
                업로드한 제품 이미지
              </p>
              <div className="mt-3 flex min-h-52 items-center justify-center rounded-lg bg-bg-primary">
                {detail.imageUrl ? (
                  <img
                    alt="업로드한 제품"
                    className="block max-h-72 max-w-full rounded-lg object-contain"
                    src={detail.imageUrl}
                  />
                ) : (
                  <FileImage className="size-8 text-text-quaternary" />
                )}
              </div>
              <p className="mt-3 text-xs font-semibold text-text-secondary">
                이미지 유형 · {detail.imageType}
              </p>
            </div>

            <div className="rounded-xl border border-border bg-bg-secondary p-4">
              <p className="text-xs font-bold text-text-secondary">
                {isViewingConfirmedTarget
                  ? '연결한 SKU'
                  : '미리보기 중인 후보 SKU'}
              </p>
              <div className="mt-3 flex items-center gap-4">
                <div className="flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-bg-tertiary">
                  {activeCandidate?.imageUrl ? (
                    <img
                      alt={activeCandidate.productName}
                      className="size-full object-cover"
                      src={activeCandidate.imageUrl}
                    />
                  ) : (
                    <FileImage className="size-6 text-text-quaternary" />
                  )}
                </div>
                <div>
                  <p className="font-mono text-xs font-bold text-text-tertiary">
                    {activeCandidate?.skuCode}
                  </p>
                  <h3 className="mt-1 text-base font-extrabold text-text-primary">
                    {activeCandidate?.productName}
                  </h3>
                  <p className="mt-1 text-sm text-text-secondary">
                    {[
                      activeCandidate?.brand,
                      [activeCandidate?.category, activeCandidate?.subCategory]
                        .filter(Boolean)
                        .join(' > '),
                    ]
                      .filter(Boolean)
                      .join(' · ') || '-'}
                  </p>
                  {activeCandidate?.price != null ? (
                    <p className="mt-1 text-sm font-semibold text-text-primary">
                      {activeCandidate.price.toLocaleString('ko-KR')}원
                    </p>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="flex flex-col items-center justify-center rounded-xl bg-bg-primary px-4 py-3 text-center lg:border lg:border-border">
              <p className="text-[11px] font-bold text-text-tertiary">유사도</p>
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
                {!isViewingConfirmedTarget ? (
                  <button
                    className="text-xs font-bold text-blue-700 hover:underline"
                    onClick={() => onPreviewCandidateChange(null)}
                    type="button"
                  >
                    연결한 SKU로 돌아가기
                  </button>
                ) : null}
              </div>
              <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                {detail.candidates.map((candidate) => {
                  const isConfirmed =
                    candidate.skuCode === detail.targetSkuCode;
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
                      onClick={() => onPreviewCandidateChange(candidate.skuId)}
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
                          <FileImage className="size-4 text-text-quaternary" />
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

          <div className="mt-5">
            <p className="text-xs font-bold text-text-secondary">
              메타데이터 비교
            </p>
            {metadataComparisonRows.length > 0 ? (
              <div className="mt-2 overflow-x-auto rounded-xl border border-neutral-100">
                <table className="w-full min-w-[640px] text-left text-xs">
                  <thead className="bg-bg-tertiary text-text-tertiary">
                    <tr>
                      <th className="px-3 py-2 font-bold">메타데이터</th>
                      <th className="px-3 py-2 font-bold">업로드 이미지</th>
                      <th className="px-3 py-2 font-bold">판정</th>
                      <th className="px-3 py-2 font-bold">연결한 SKU</th>
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
            ) : (
              <p className="mt-2 text-sm text-text-tertiary">
                비교할 메타데이터가 없습니다.
              </p>
            )}
          </div>
        </>
      ) : (
        <>
          <dl className="mt-6 grid gap-3 sm:grid-cols-2">
            <ReviewValue label="등록 방식">신규 SKU 생성</ReviewValue>
            <ReviewValue label="이미지 유형">{detail.imageType}</ReviewValue>
            <ReviewValue label="브랜드">
              {detail.proposedBrand ?? '-'}
            </ReviewValue>
            <ReviewValue label="가격">
              {formatPrice(detail.proposedPrice)}
            </ReviewValue>
            <ReviewValue label="카테고리">
              {[detail.proposedCategory, detail.proposedSubCategory]
                .filter(Boolean)
                .join(' · ') || '-'}
            </ReviewValue>
          </dl>

          <div className="mt-4">
            <p className="text-[11px] font-bold text-text-tertiary">
              세부 속성
            </p>
            {Object.keys(detail.proposedAttributes).length > 0 ? (
              <dl className="mt-2 grid gap-3 sm:grid-cols-2">
                {Object.entries(detail.proposedAttributes).map(
                  ([key, value]) => (
                    <ReviewValue key={key} label={ATTRIBUTE_LABELS[key] ?? key}>
                      {typeof value === 'string' ? value : String(value)}
                    </ReviewValue>
                  ),
                )}
              </dl>
            ) : (
              <p className="mt-2 text-sm text-text-tertiary">
                등록된 세부 속성이 없습니다.
              </p>
            )}
          </div>
        </>
      )}

      {detail.status === 'REJECTED' ? (
        <div className="mt-6 rounded-xl border border-danger-200 bg-danger-20 p-4">
          <p className="text-xs font-bold text-danger-600">반려 사유</p>
          <p className="mt-1.5 text-sm font-medium leading-6 text-text-secondary">
            {detail.rejectReason}
          </p>
        </div>
      ) : null}

      {detail.status === 'APPROVED' ? (
        <div className="mt-6 flex items-center gap-2 rounded-xl border border-success-50 bg-success-50/50 p-4 text-sm font-semibold text-success-600">
          <Check className="size-4" />
          카탈로그에 반영되었습니다. 이후 일반 태깅 검색에도 사용할 수 있습니다.
        </div>
      ) : null}

      {detail.status === 'PENDING' ? (
        <div className="mt-8 border-t border-border pt-5">
          {isSuperAdmin ? (
            <>
              {isRejecting ? (
                <div className="rounded-xl border border-danger-200 bg-danger-20 p-4">
                  <label
                    className="text-xs font-bold text-danger-600"
                    htmlFor="reject-reason"
                  >
                    반려 사유
                  </label>
                  <textarea
                    className="mt-2 min-h-24 w-full rounded-lg border border-danger-200 bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none focus:border-danger-600"
                    id="reject-reason"
                    onChange={(event) =>
                      onRejectReasonChange(event.target.value)
                    }
                    placeholder="수정이 필요한 내용을 입력하세요."
                    value={rejectReason}
                  />
                  <div className="mt-3 flex justify-end gap-2">
                    <Button
                      disabled={isBusy}
                      onClick={() => onRejectingChange(false)}
                      size="sm"
                      variant="neutral-outlined"
                    >
                      취소
                    </Button>
                    <Button
                      className="border-danger-600 bg-danger-600 hover:border-danger-600 hover:bg-danger-600"
                      disabled={
                        isBusy ||
                        !rejectReason.trim() ||
                        !isViewingConfirmedTarget
                      }
                      onClick={onReject}
                      size="sm"
                    >
                      반려 확정
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap justify-end gap-2">
                  <Button
                    disabled={isBusy || !isViewingConfirmedTarget}
                    onClick={() => onRejectingChange(true)}
                    variant="neutral-outlined"
                  >
                    반려
                  </Button>
                  <Button
                    disabled={isBusy || !isViewingConfirmedTarget}
                    endDecorator={<Check className="size-4" />}
                    onClick={onApprove}
                  >
                    승인하고 카탈로그 반영
                  </Button>
                </div>
              )}
            </>
          ) : (
            <p className="rounded-xl bg-bg-muted px-4 py-3 text-sm font-semibold text-text-secondary">
              시스템 관리자의 승인 후 시스템 카탈로그와 태깅 검색에 반영됩니다.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
};

const ReviewValue = ({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) => (
  <div className="rounded-xl bg-bg-secondary px-3.5 py-3">
    <dt className="text-[11px] font-bold text-text-tertiary">{label}</dt>
    <dd className="mt-1 truncate text-sm font-semibold text-text-primary">
      {children}
    </dd>
  </div>
);
