import { useEffect, useState } from 'react';
import manifest from './_screens.json';
import type { Screen } from './_shared';
import { screenById } from './_shared';
import { ConsumerView } from './ConsumerViews';
import { LegacyView } from './LegacyViews';
import { AdminView, OwnerView } from './OperationsViews';
import { DetailView, SuiteFrame, screenHref } from './_shared';
import './_suite.css';

const screens = manifest.screens as Screen[];

function readScreenId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('screen') ?? 'C001';
}

export function Suite() {
  const [screenId, setScreenId] = useState(readScreenId);
  useEffect(() => {
    const onPopState = () => setScreenId(readScreenId());
    window.addEventListener('popstate', onPopState);
    const onClick = (event: MouseEvent) => {
      const link = (event.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="?screen="]');
      if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const url = new URL(link.href);
      window.history.pushState({}, '', url);
      setScreenId(url.searchParams.get('screen') ?? 'C001');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    document.addEventListener('click', onClick);
    return () => {
      window.removeEventListener('popstate', onPopState);
      document.removeEventListener('click', onClick);
    };
  }, []);

  const screen = screenById(screens, screenId);
  if (screen.id.startsWith('L') || /legacy|alias|shell/i.test(screen.kind)) return <LegacyView screen={screen} allScreens={screens}/>;
  if (screen.role === '사용자') {
    if (screen.view === 'detail' || screen.view === 'detail-month' || screen.view === 'detail-missing') {
      return <DetailView screen={screen} month={screen.view === 'detail-month'} missing={screen.view === 'detail-missing'}/>;
    }
    return <ConsumerView screen={screen}/>;
  }
  if (screen.role === '임대인') return <OwnerView screen={screen}/>;
  if (screen.role === '관리자') return <AdminView screen={screen}/>;
  return <SuiteFrame screen={screen}><main className="hs-main"><h1>{screen.title}</h1><a className="hs-btn" href={screenHref('C001')}>검색 화면</a></main></SuiteFrame>;
}

export default Suite;
