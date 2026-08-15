import { Clock3, PlusSquare } from 'lucide-react';

import type { LucideIcon } from 'lucide-react';

type SidebarMenu = {
  Icon: LucideIcon;
  id: 'tagging' | 'history';
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
