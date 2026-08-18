import { useEffect, useMemo, useState } from 'react';
import { Check, ClipboardCheck, Eye, ImageOff, X } from 'lucide-react';

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
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { cn } from '@/lib/utils';

const statuses: Array<{ label: string; value: ApprovalStatus | 'ALL' }> = [
  { label: '승인 대기', value: 'PENDING' },
  { label: '승인 완료', value: 'ACTIVE' },
  { label: '반려', value: 'REJECTED' },
  { label: '전체', value: 'ALL' },
];

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

const formatDate = (value: string): string =>
  new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));

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

  const session = user?.session;
  const isSuperAdmin = user?.role === 'SUPER_ADMIN';
  const selectedItem = useMemo(
    () => items.find((item) => item.requestId === selectedId),
    [items, selectedId],
  );

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
        if (isMounted) setDetail(nextDetail);
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

      <div className="mt-5 grid min-h-[580px] gap-5 xl:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.5fr)]">
        <section className="studio-surface min-h-0 p-3">
          <div className="flex items-center justify-between px-2 pb-3 pt-1">
            <h2 className="text-sm font-extrabold text-text-primary">
              승인 요청
            </h2>
            <span className="text-xs font-semibold text-text-tertiary">
              {isLoading ? '불러오는 중' : `${items.length}건`}
            </span>
          </div>
          <div className="max-h-[650px] space-y-2 overflow-y-auto pr-1">
            {items.map((item) => (
              <button
                aria-pressed={selectedId === item.requestId}
                className={cn(
                  'w-full rounded-xl border p-4 text-left transition-colors',
                  selectedId === item.requestId
                    ? 'border-blue-600 bg-blue-50 shadow-[0_0_0_1px_#2563eb]'
                    : 'border-border bg-bg-primary hover:border-blue-300 hover:bg-bg-hover',
                )}
                key={item.requestId}
                onClick={() => setSelectedId(item.requestId)}
                type="button"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-bold text-text-primary">
                      {item.productName}
                    </span>
                    <span className="mt-1 block font-mono text-[11px] text-text-tertiary">
                      {item.skuCode} · 객체 {item.objectIndex + 1}
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
                <span className="mt-3 block text-xs text-text-secondary">
                  {item.category ?? '카테고리 미지정'} · {item.originName}
                </span>
                <span className="mt-2 block text-[11px] text-text-tertiary">
                  {formatDate(item.requestedAt)}
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

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl bg-bg-tertiary p-4">
                  <p className="text-xs font-bold text-text-secondary">
                    원본의 선택 객체
                  </p>
                  <div className="mt-3 flex min-h-52 items-center justify-center overflow-hidden rounded-lg bg-bg-primary">
                    {detail.sceneImage.imageUrl ? (
                      <img
                        alt={detail.sceneImage.originName}
                        className="max-h-72 w-full object-contain"
                        src={detail.sceneImage.imageUrl}
                      />
                    ) : (
                      <ImageOff className="size-8 text-text-quaternary" />
                    )}
                  </div>
                  <p className="mt-3 text-xs font-semibold text-text-secondary">
                    {detail.object.category ?? '카테고리 미지정'} · 객체{' '}
                    {detail.object.objectIndex + 1}
                  </p>
                </div>
                <div className="rounded-xl bg-bg-tertiary p-4">
                  <p className="text-xs font-bold text-text-secondary">
                    연결할 SKU 이미지
                  </p>
                  <div className="mt-3 flex min-h-52 items-center justify-center rounded-lg bg-bg-primary">
                    <FurnitureArtwork
                      imageUrl={detail.sku.imageUrl}
                      kind={null}
                    />
                  </div>
                  <p className="mt-3 text-xs font-semibold text-text-secondary">
                    유사도{' '}
                    {detail.similarityScore === null
                      ? '-'
                      : `${Math.round(detail.similarityScore * 100)}%`}
                  </p>
                </div>
              </div>

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
                {detail.xaiResult?.summary ? (
                  <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 px-4 py-3 text-sm">
                    <dt className="text-text-tertiary">매칭 근거</dt>
                    <dd className="leading-6 text-text-primary">
                      {detail.xaiResult.summary}
                    </dd>
                  </div>
                ) : null}
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
                          disabled={!rejectReason.trim() || isLoading}
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
                        disabled={isLoading}
                        onClick={() => setIsRejecting(true)}
                        startDecorator={<X size={16} />}
                        variant="neutral-outlined"
                      >
                        반려
                      </Button>
                      <Button
                        disabled={isLoading}
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
