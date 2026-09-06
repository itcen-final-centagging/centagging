import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Check,
  ChevronRight,
  CircleAlert,
  FileImage,
  ImagePlus,
  ImageUp,
  LoaderCircle,
  PackagePlus,
  Send,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  extractSkuMetadata,
  fetchCatalogSkus,
  type CatalogSku,
} from '@/features/catalog/api/catalog';
import {
  approveProductImageSubmission,
  configureProductImageSubmission,
  getProductImageSubmission,
  listProductImageSubmissions,
  rejectProductImageSubmission,
  submitProductImageSubmission,
  uploadProductImageDrafts,
  type ProductImageSubmission,
  type ProductImageSubmissionDraft,
  type ProductImageSubmissionStatus,
  type ProductImageTargetType,
  type ProductImageType,
} from '@/features/productImageSubmissions/api/productImageSubmissions';
import { SkuCatalogSearchDialog } from '@/features/productImageSubmissions/components/SkuCatalogSearchDialog';
import {
  CATEGORIES,
  getAllowedValues,
  getCategoryAttributeKeys,
  getSubCategories,
  withCurrentValue,
} from '@/features/tagging/constants/catalogSpec';
import {
  ATTRIBUTE_LABELS,
  COMMON_ATTRIBUTE_KEYS,
} from '@/features/tagging/constants/skuAttributes';
import { cn } from '@/lib/utils';

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
  targetType: 'EXISTING',
});

const draftFromSubmission = (
  submission: ProductImageSubmission,
): ProductImageSubmissionDraft => {
  const targetType = submission.targetType ?? 'EXISTING';
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
  const [catalog, setCatalog] = useState<CatalogSku[]>([]);
  const [draft, setDraft] = useState<ProductImageSubmissionDraft>(emptyDraft);
  const [error, setError] = useState<string>();
  const [isBusy, setIsBusy] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

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
    if (!session) return undefined;
    let isMounted = true;
    void fetchCatalogSkus(session)
      .then((nextCatalog) => {
        if (isMounted) setCatalog(nextCatalog);
      })
      .catch(() => {
        // SKU 선택지는 보조 데이터이므로, 목록 조회 실패가 등록 큐를 막지 않습니다.
      });
    return () => {
      isMounted = false;
    };
  }, [session]);

  useEffect(() => {
    if (!session || !selectedId) return undefined;
    let isMounted = true;
    void getProductImageSubmission(session, selectedId)
      .then((nextDetail) => {
        if (!isMounted) return;
        setDetail(nextDetail);
        setDraft(draftFromSubmission(nextDetail));
        setIsRejecting(false);
        setRejectReason('');
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

  const replaceItem = (nextDetail: ProductImageSubmission) => {
    setDetail(nextDetail);
    setDraft(draftFromSubmission(nextDetail));
    setItems((currentItems) =>
      currentItems.map((item) =>
        item.submissionId === nextDetail.submissionId ? nextDetail : item,
      ),
    );
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

  const handleExtractAttributes = async () => {
    if (!session || !detail) return;
    setIsExtracting(true);
    setError(undefined);
    try {
      const imageBlob = await fetch(detail.imageUrl).then((response) =>
        response.blob(),
      );
      const extracted = await extractSkuMetadata(session, imageBlob);
      setDraft((current) => ({
        ...current,
        proposedAttributes: extracted.attributes,
        proposedCategory: extracted.category ?? current.proposedCategory,
        proposedSubCategory:
          extracted.subCategory ?? current.proposedSubCategory,
      }));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'AI 속성 추출에 실패했습니다.',
      );
    } finally {
      setIsExtracting(false);
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

      <div className="mt-5 grid min-h-[620px] gap-5 xl:grid-cols-[minmax(295px,0.7fr)_minmax(0,1.5fr)]">
        <section className="studio-surface min-h-0 p-3">
          <div className="flex items-center justify-between px-2 pb-3 pt-1">
            <h2 className="text-sm font-extrabold text-text-primary">
              등록 큐
            </h2>
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
                제품 이미지를 업로드하면 이곳에서 하나씩 등록 정보를 입력할 수
                있습니다.
              </p>
            </div>
          ) : null}
          <div className="max-h-[710px] space-y-2 overflow-y-auto pr-1">
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
            <div className="grid min-h-[620px] lg:grid-cols-[minmax(230px,0.75fr)_minmax(0,1.25fr)]">
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

              <div className="p-5">
                {detail.status === 'DRAFT' ? (
                  <DraftEditor
                    catalog={catalog}
                    draft={draft}
                    isBusy={isBusy}
                    isExtracting={isExtracting}
                    onChange={setDraft}
                    onExtractAttributes={() => {
                      void handleExtractAttributes();
                    }}
                    onSave={() => {
                      void saveDraft();
                    }}
                    onSubmit={() => {
                      void handleSubmit();
                    }}
                  />
                ) : (
                  <SubmissionReview
                    detail={detail}
                    isBusy={isBusy}
                    isRejecting={isRejecting}
                    isSuperAdmin={isSuperAdmin}
                    onApprove={() => {
                      void handleApprove();
                    }}
                    onReject={() => {
                      void handleReject();
                    }}
                    onRejectingChange={setIsRejecting}
                    onRejectReasonChange={setRejectReason}
                    rejectReason={rejectReason}
                  />
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

type DraftEditorProps = {
  catalog: CatalogSku[];
  draft: ProductImageSubmissionDraft;
  isBusy: boolean;
  isExtracting: boolean;
  onChange: (draft: ProductImageSubmissionDraft) => void;
  onExtractAttributes: () => void;
  onSave: () => void;
  onSubmit: () => void;
};

const DraftEditor = ({
  catalog,
  draft,
  isBusy,
  isExtracting,
  onChange,
  onExtractAttributes,
  onSave,
  onSubmit,
}: DraftEditorProps) => {
  const [isCatalogSearchOpen, setIsCatalogSearchOpen] = useState(false);

  const setField = <Key extends keyof ProductImageSubmissionDraft>(
    field: Key,
    value: ProductImageSubmissionDraft[Key],
  ) => onChange({ ...draft, [field]: value });

  const selectedTarget = catalog.find(
    (sku) => sku.skuCode === draft.targetSkuCode,
  );

  const handleTargetTypeChange = (nextTargetType: ProductImageTargetType) => {
    onChange({
      ...draft,
      imageType:
        nextTargetType === 'NEW'
          ? 'MAIN'
          : draft.imageType === 'MAIN'
            ? 'ANGLE'
            : draft.imageType,
      targetType: nextTargetType,
    });
  };

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
            상품 등록 정보
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            이미지 한 장씩 등록 방식을 정한 뒤 승인 요청을 보냅니다.
          </p>
        </div>
        {draft.targetType === 'NEW' ? (
          <span className="inline-flex min-h-9 items-center rounded-lg border border-border bg-bg-muted px-3 text-xs font-semibold text-text-secondary">
            대표 이미지
          </span>
        ) : (
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
        )}
      </div>

      <fieldset className="mt-6">
        <legend className={fieldLabelClassName}>등록 방식</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {(
            [
              ['EXISTING', '기존 SKU에 연결'],
              ['NEW', '신규 상품으로 등록'],
            ] as Array<[ProductImageTargetType, string]>
          ).map(([value, label]) => (
            <label
              className={cn(
                'flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-3 text-sm font-bold transition-colors',
                draft.targetType === value
                  ? 'border-blue-600 bg-blue-50 text-blue-800'
                  : 'border-border bg-bg-primary text-text-secondary hover:border-blue-300',
              )}
              key={value}
            >
              <input
                checked={draft.targetType === value}
                className="accent-blue-700"
                name="target-type"
                onChange={() => handleTargetTypeChange(value)}
                type="radio"
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      {draft.targetType === 'EXISTING' ? (
        <div className="mt-5">
          <div className="flex items-end justify-between gap-3">
            <label className={fieldLabelClassName} htmlFor="target-sku">
              연결할 SKU
            </label>
            <button
              className="text-xs font-bold text-blue-700 hover:underline"
              onClick={() => setIsCatalogSearchOpen(true)}
              type="button"
            >
              전체 카탈로그 검색
            </button>
          </div>
          <select
            className={fieldClassName}
            id="target-sku"
            onChange={(event) =>
              setField('targetSkuCode', event.target.value || null)
            }
            value={draft.targetSkuCode ?? ''}
          >
            <option value="">등록된 SKU를 선택하세요</option>
            {catalog.map((sku) => (
              <option key={sku.skuId} value={sku.skuCode}>
                {sku.skuCode} · {sku.productName}
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs text-text-tertiary">
            시스템에 이미 등록된 SKU에 새 제품 이미지를 연결합니다.
          </p>

          {selectedTarget ? (
            <div className="mt-3 flex items-center gap-3 rounded-xl border border-border bg-bg-secondary p-3">
              <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-bg-tertiary">
                {selectedTarget.mainImageUrl ? (
                  <img
                    alt="선택한 SKU 대표 이미지"
                    className="h-full w-full object-cover"
                    src={selectedTarget.mainImageUrl}
                  />
                ) : (
                  <FileImage className="size-5 text-text-quaternary" />
                )}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-bold text-text-primary">
                  {selectedTarget.productName}
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-text-tertiary">
                  {selectedTarget.skuCode}
                </p>
              </div>
            </div>
          ) : null}

          {isCatalogSearchOpen ? (
            <SkuCatalogSearchDialog
              onClose={() => setIsCatalogSearchOpen(false)}
              onSelect={(detail) => {
                setField('targetSkuCode', detail.skuCode);
                setIsCatalogSearchOpen(false);
              }}
            />
          ) : null}
        </div>
      ) : (
        <>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field
              label="신규 SKU 코드"
              onChange={(value) => setField('proposedSkuCode', value || null)}
              placeholder="예: CHR-2042"
              value={draft.proposedSkuCode ?? ''}
            />
            <Field
              label="상품명"
              onChange={(value) =>
                setField('proposedProductName', value || null)
              }
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
              <label
                className={fieldLabelClassName}
                htmlFor="product-sub-category"
              >
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

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
            <div>
              <p className="text-sm font-bold text-blue-900">AI 속성 추출</p>
              <p className="mt-0.5 text-xs text-blue-800/80">
                등록 이미지에서 대분류·소분류·속성을 한 번에 추출합니다. 추출
                결과는 아래에서 직접 수정할 수 있습니다.
              </p>
            </div>
            <Button
              disabled={isExtracting}
              onClick={onExtractAttributes}
              size="sm"
              startDecorator={
                isExtracting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Sparkles className="size-4" />
                )
              }
              variant="neutral-outlined"
            >
              {isExtracting ? '추출 중' : 'AI로 속성 추출하기'}
            </Button>
          </div>

          {draft.proposedCategory ? (
            <fieldset className="mt-5">
              <legend className={fieldLabelClassName}>상세 속성</legend>
              <p className="mt-1 text-xs text-text-tertiary">
                대분류를 바꾸면 아래 속성은 초기화됩니다. 카테고리에 맞게 다시
                선택해 주세요.
              </p>
              <div className="mt-2 grid gap-4 sm:grid-cols-2">
                {attributeKeys.map((key) => {
                  const currentValue = draft.proposedAttributes[key];
                  return (
                    <label className={fieldLabelClassName} key={key}>
                      {ATTRIBUTE_LABELS[key] ?? key}
                      <select
                        className={fieldClassName}
                        onChange={(event) =>
                          handleAttributeChange(key, event.target.value)
                        }
                        value={
                          typeof currentValue === 'string' ? currentValue : ''
                        }
                      >
                        <option value="">선택 안 함</option>
                        {withCurrentValue(
                          getAllowedValues(draft.proposedCategory, key),
                          typeof currentValue === 'string'
                            ? currentValue
                            : undefined,
                        ).map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ) : null}
        </>
      )}

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
  onReject: () => void;
  onRejectingChange: (isRejecting: boolean) => void;
  onRejectReasonChange: (rejectReason: string) => void;
  rejectReason: string;
};

const SubmissionReview = ({
  detail,
  isBusy,
  isRejecting,
  isSuperAdmin,
  onApprove,
  onReject,
  onRejectingChange,
  onRejectReasonChange,
  rejectReason,
}: SubmissionReviewProps) => {
  const title =
    detail.targetProductName ?? detail.proposedProductName ?? '상품 정보 없음';
  const code = detail.targetSkuCode ?? detail.proposedSkuCode ?? 'SKU 미지정';

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

      {detail.targetType === 'EXISTING' ? (
        <div className="mt-5">
          <p className="text-[11px] font-bold text-text-tertiary">
            연결 대상 대표 이미지
          </p>
          <div className="mt-2 flex size-24 items-center justify-center overflow-hidden rounded-xl border border-border bg-bg-tertiary">
            {detail.targetMainImageUrl ? (
              <img
                alt="연결 대상 SKU 대표 이미지"
                className="h-full w-full object-cover"
                src={detail.targetMainImageUrl}
              />
            ) : (
              <FileImage className="size-6 text-text-quaternary" />
            )}
          </div>
        </div>
      ) : null}

      <dl className="mt-6 grid gap-3 sm:grid-cols-2">
        <ReviewValue label="등록 방식">
          {detail.targetType === 'EXISTING'
            ? '기존 SKU 이미지 추가'
            : '신규 SKU 생성'}
        </ReviewValue>
        <ReviewValue label="이미지 유형">{detail.imageType}</ReviewValue>
        <ReviewValue label="브랜드">
          {(detail.targetType === 'EXISTING'
            ? detail.targetBrand
            : detail.proposedBrand) ?? '-'}
        </ReviewValue>
        <ReviewValue label="가격">
          {formatPrice(
            detail.targetType === 'EXISTING'
              ? detail.targetPrice
              : detail.proposedPrice,
          )}
        </ReviewValue>
        <ReviewValue label="카테고리">
          {[
            detail.targetType === 'EXISTING'
              ? detail.targetCategory
              : detail.proposedCategory,
            detail.targetType === 'EXISTING'
              ? detail.targetSubCategory
              : detail.proposedSubCategory,
          ]
            .filter(Boolean)
            .join(' · ') || '-'}
        </ReviewValue>
      </dl>

      {detail.targetType === 'NEW' ? (
        <div className="mt-4">
          <p className="text-[11px] font-bold text-text-tertiary">세부 속성</p>
          {Object.keys(detail.proposedAttributes).length > 0 ? (
            <dl className="mt-2 grid gap-3 sm:grid-cols-2">
              {Object.entries(detail.proposedAttributes).map(([key, value]) => (
                <ReviewValue key={key} label={ATTRIBUTE_LABELS[key] ?? key}>
                  {typeof value === 'string' ? value : String(value)}
                </ReviewValue>
              ))}
            </dl>
          ) : (
            <p className="mt-2 text-sm text-text-tertiary">
              등록된 세부 속성이 없습니다.
            </p>
          )}
        </div>
      ) : null}

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
                      disabled={isBusy || !rejectReason.trim()}
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
                    disabled={isBusy}
                    onClick={() => onRejectingChange(true)}
                    variant="neutral-outlined"
                  >
                    반려
                  </Button>
                  <Button
                    disabled={isBusy}
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
