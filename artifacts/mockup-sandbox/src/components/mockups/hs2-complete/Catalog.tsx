import { useMemo, useState } from 'react';
import { ArrowUpRight, ChevronDown, FileText, Search } from 'lucide-react';
import manifest from './_screens.json';
import type { Screen } from './_shared';
import { Header, screenHref } from './_shared';
import './_suite.css';

const screens = manifest.screens as Screen[];
const roles = [
  { title: '사용자', root: 'C001', anchor: 'catalog-consumer' },
  { title: '임대인', root: 'O001', anchor: 'catalog-owner' },
  { title: '관리자', root: 'A001', anchor: 'catalog-admin' },
];
const displayTitle = (screen: Screen) => {
  const title = screen.title.replace(/&amp;/g, '&').replace(/\{\{[^}]*\}\}/g, '').trim();
  if (title) return title;
  return screen.source_outline?.find((item) => !/^(검색|저장|제출|등록|확인|변경|로그인|닫기|새로고침|openModal)$/i.test(item.trim()))?.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '').trim() || '업무 정보';
};

function ReviewMetadata({ screen }: { screen: Screen }) {
  return <div className="hs-catalog-meta">
    <span className="hs-review-badge">{screen.design_status ?? '검수 대기'}</span>
    <div><small>{screen.function_status ?? '디자인 시안 · 기능 완료 판정 아님'}</small></div>
  </div>;
}

function TreeNode({ screen, query, depth = 0, all }: { screen: Screen; query: string; depth?: number; all: Screen[] }) {
  const children = all.filter((item) => item.parent === screen.id && item.id !== screen.id);
  const matches = !query || `${screen.id} ${displayTitle(screen)} ${screen.view} ${screen.kind}`.toLowerCase().includes(query.toLowerCase());
  const childMatches = children.some((child) => childMatchesInTree(child, query, all));
  if (query && !matches && !childMatches) return null;
  return <div className="hs-tree-node" style={{marginLeft: depth ? 17 : 0}}>
    <div className="hs-catalog-item">
      <a className="hs-catalog-id" href={`/__mockup/preview/hs2-complete/Suite${screenHref(screen.id)}`}>{screen.id}</a>
      <a href={`/__mockup/preview/hs2-complete/Suite${screenHref(screen.id)}`}>{displayTitle(screen)}</a>
      <small>{screen.kind} · {screen.view}</small>
      <ReviewMetadata screen={screen}/>
    </div>
    {children.length > 0 && <details open={!!query || depth === 0} className="hs-tree-children">
      <summary><ChevronDown size={15}/> 하위 화면 {children.length}개</summary>
      {children.map((child) => <TreeNode key={child.id} screen={child} query={query} depth={depth + 1} all={all}/>)}
    </details>}
  </div>;
}

function childMatchesInTree(screen: Screen, query: string, all: Screen[]): boolean {
  if (!query) return true;
  const children = all.filter((item) => item.parent === screen.id && item.id !== screen.id);
  return `${screen.id} ${screen.title} ${screen.view} ${screen.kind}`.toLowerCase().includes(query.toLowerCase()) || children.some((child) => childMatchesInTree(child, query, all));
}

export function Catalog() {
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('전체');
  const counts = useMemo(() => roles.map((role) => ({ ...role, count: screens.filter((screen) => screen.role === role.title).length })), []);
  const filtered = roleFilter === '전체' ? counts : counts.filter((item) => item.title === roleFilter);
  return <div className="hs-suite" data-screen-id="CATALOG" data-screen-kind="index" data-testid="hs-screen-catalog">
    <Header currentRole=""/>
    <main className="hs-catalog">
      <div className="hs-title-row"><div><p className="hs-kicker">HOME &amp; STAY · 화면 검토 목차</p><h1>전체 화면 한눈에 보기</h1><p>역할별 화면, 세부 탭과 팝업을 독립적인 주소로 열어볼 수 있습니다.</p></div><div className="hs-chip">{screens.length}개 화면</div></div>
      <div className="hs-notice" style={{marginBottom:22}}>아래 검수 상태와 기능 상태는 화면 리뷰용 메타데이터입니다. 이 목차는 기능 완료나 실제 운영 권한을 의미하지 않습니다.</div>
      <div className="hs-catalog-layout">
        <aside className="hs-catalog-roles">
          <a href="#catalog-consumer">사용자 <span>{counts[0].count}</span></a>
          <a href="#catalog-owner">임대인 <span>{counts[1].count}</span></a>
          <a href="#catalog-admin">관리자 <span>{counts[2].count}</span></a>
          <div style={{padding:12,borderTop:'1px solid var(--hs-line)',marginTop:8}}>
            <label className="hs-field">역할 검색
              <select value={roleFilter} onChange={(e)=>setRoleFilter(e.target.value)}>{['전체','사용자','임대인','관리자'].map((role)=><option key={role}>{role}</option>)}</select>
            </label>
          </div>
        </aside>
        <div>
          <label className="hs-field" style={{marginBottom:18}}>화면 ID 또는 이름 검색
            <div style={{position:'relative'}}><Search size={18} style={{position:'absolute',left:13,top:15}}/><input style={{paddingLeft:40}} type="search" value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="예: C037, 예약, 시설"/></div>
          </label>
          {filtered.map((role)=> {
            const root = screens.find((screen)=>screen.id === role.root);
            return root && <section className="hs-catalog-group" id={role.anchor} key={role.title}>
              <h2>{role.title} <small>{role.count} screens</small></h2>
              <TreeNode screen={root} all={screens} query={query}/>
            </section>;
          })}
          {query && screens.filter((screen)=>`${screen.id} ${screen.title} ${screen.view}`.toLowerCase().includes(query.toLowerCase())).length === 0 && <div className="hs-empty-state"><FileText size={35}/><h2>검색 결과가 없습니다</h2><p>다른 ID나 화면 이름으로 다시 찾아보세요.</p></div>}
        </div>
      </div>
      <p style={{marginTop:24}}><a className="hs-btn secondary" href="/__mockup/preview/hs2-complete/Suite?screen=C001">사용자 검색 미리보기 <ArrowUpRight size={16}/></a></p>
    </main>
  </div>;
}

export default Catalog;
