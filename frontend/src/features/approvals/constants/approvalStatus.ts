/**
 * 승인(approval) 상태의 화면 표기 규칙입니다.
 *
 * 승인 관리 화면과 검수 이력 화면이 같은 라벨·색상을 쓰도록 한곳에 모읍니다.
 * 값 자체는 DB의 `approval.status`(ck_approval_status)와 같습니다.
 */

import type { ApprovalStatus } from '@/features/approvals/api/approvals';

export const APPROVAL_STATUS_LABELS: Record<ApprovalStatus, string> = {
  ACTIVE: '승인 완료',
  PENDING: '승인 대기',
  REJECTED: '반려',
};

export const APPROVAL_STATUS_STYLES: Record<ApprovalStatus, string> = {
  ACTIVE: 'bg-success-50 text-success-600',
  PENDING: 'bg-warning-50 text-warning-600',
  REJECTED: 'bg-danger-20 text-danger-600',
};
