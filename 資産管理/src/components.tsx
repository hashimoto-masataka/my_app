import { LayoutDashboard, WalletCards, ChartNoAxesCombined, Settings, Plus, ShieldCheck, Waves, X, Search, Pencil, Trash2, ArrowUpRight, Database, Download, Upload, UserRound, CalendarDays, ChevronLeft, ChevronRight, ReceiptText } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Page } from './types';

export const navItems = [
  { id: 'dashboard' as Page, label: 'ダッシュボード', icon: LayoutDashboard },
  { id: 'assets' as Page, label: '資産一覧', icon: WalletCards },
  { id: 'income' as Page, label: '収支管理', icon: ReceiptText },
  { id: 'history' as Page, label: '推移・履歴', icon: ChartNoAxesCombined },
  { id: 'settings' as Page, label: '設定', icon: Settings },
];

export function Sidebar({ page, setPage }: { page: Page; setPage: (p: Page) => void }) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark"><Waves size={22}/></span><span>Aqua<span>Asset</span></span></div>
    <div className="workspace"><span className="avatar">H</span><div><b>マイポートフォリオ</b><small>ローカル保存</small></div></div>
    <nav>{navItems.map(({ id, label, icon: Icon }) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}><Icon size={18}/><span>{label}</span></button>)}</nav>
    <div className="secure"><ShieldCheck size={17}/><div><b>データは安全です</b><small>端末内にのみ保存</small></div></div>
  </aside>;
}

export function Header({ title, subtitle, action, actionLabel }: { title: string; subtitle: string; action?: () => void; actionLabel?: string }) {
  const label=actionLabel??(title==='推移・履歴'?'過去データを登録':'資産を追加');
  return <header className="header"><div><h1>{title}</h1><p>{subtitle}</p></div>{action && <button className="primary" onClick={action}><Plus size={18}/>{label}</button>}</header>;
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section>; }
export const Icons = { X, Search, Pencil, Trash2, ArrowUpRight, Database, Download, Upload, Plus, UserRound, CalendarDays, ChevronLeft, ChevronRight };
