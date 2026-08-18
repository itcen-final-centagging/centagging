import {
  ClipboardCheck,
  Clock3,
  Images,
  PlusSquare,
  UploadCloud,
} from 'lucide-react';

import type { LucideIcon } from 'lucide-react';

export type SidebarMenu = {
  Icon: LucideIcon;
  id: 'tagging' | 'history' | 'approvals' | 'catalog' | 'product-submissions';
  label: string;
  to: string;
};

export const sidebarMenus: SidebarMenu[] = [
  {
    id: 'tagging',
    Icon: PlusSquare,
    label: '새 태깅 작업',
    to: '/',
  },
  {
    id: 'history',
    Icon: Clock3,
    label: '검수 이력',
    to: '/history',
  },
];

export const adminSidebarMenus: SidebarMenu[] = [
  {
    id: 'product-submissions',
    Icon: UploadCloud,
    label: '제품 이미지 등록',
    to: '/admin/product-images',
  },
  {
    id: 'catalog',
    Icon: Images,
    label: '등록 상품',
    to: '/admin',
  },
  {
    id: 'approvals',
    Icon: ClipboardCheck,
    label: '태깅 승인 관리',
    to: '/admin/approvals',
  },
];
