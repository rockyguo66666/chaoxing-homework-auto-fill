window.__ModuleLoader__.load({
  id: '@local/chaoxing-homework-panel',
  factory(require) {
    const React = require('react');
    const h = React.createElement;
    const NS = 'chaoxing.homework.panel';
    const PANEL_ID = 'chaoxing-homework';

    const zh = {
      'panel': '学习通自动化',
      'page.title': '学习通自动化',
      'page.subtitle': '作业清单来自本机每日扫描，点击卡片直达学习通作业页',
      'stat.all': '全部作业',
      'stat.pending': '未提交',
      'stat.submitted': '已提交',
      'filter.all': '全部',
      'filter.pending': '未交',
      'filter.submitted': '已交',
      'search': '搜索课程或作业',
      'refresh': '刷新',
      'refreshing': '刷新中…',
      'loading': '正在读取本机扫描结果…',
      'scan.at': '扫描于',
      'scan.stale': '数据可能已过期（超过 26 小时）',
      'source': '数据源',
      'empty.none': '暂无作业数据：本机还没有生成扫描结果 result.json',
      'empty.filter': '没有符合条件的作业',
      'error': '读取失败',
      'status.pending': '未提交',
      'status.submitted': '已提交',
      'status.awaiting': '已提交 · 待批阅',
      'status.other': '状态未知',
      'deadline.unknown': '截止未知',
      'deadline.semester': '截止：学期末',
      'deadline.closed': '已截止 · 不可作答',
      'deadline.label': '截止',
      'no.link': '该作业没有直达链接',
      'open': '打开作业页',
    };
    const en = {
      'panel': 'Chaoxing Homework',
      'page.title': 'Chaoxing Homework',
      'page.subtitle': 'From the local daily scan; click a card to open the homework page',
      'stat.all': 'All',
      'stat.pending': 'Not submitted',
      'stat.submitted': 'Submitted',
      'filter.all': 'All',
      'filter.pending': 'Pending',
      'filter.submitted': 'Submitted',
      'search': 'Search course or homework',
      'refresh': 'Refresh',
      'refreshing': 'Refreshing…',
      'loading': 'Reading the local scan result…',
      'scan.at': 'Scanned at',
      'scan.stale': 'Data may be stale (over 26 hours)',
      'source': 'Source',
      'empty.none': 'No data: no result.json on this machine yet',
      'empty.filter': 'No matching homework',
      'error': 'Read failed',
      'status.pending': 'Not submitted',
      'status.submitted': 'Submitted',
      'status.awaiting': 'Submitted · awaiting review',
      'status.other': 'Unknown status',
      'deadline.unknown': 'Deadline unknown',
      'deadline.semester': 'Deadline: end of semester',
      'deadline.closed': 'Closed · no longer answerable',
      'deadline.label': 'Due',
      'no.link': 'No direct link for this homework',
      'open': 'Open homework',
    };

    const CSS = [
      '.cxhp-page{box-sizing:border-box;height:100%;overflow-y:auto;padding:28px 32px 48px;background:var(--dsw-alias-bg-base);color:var(--dsw-alias-label-primary);font-family:inherit;}',
      '.cxhp-page *{box-sizing:border-box;}',
      '.cxhp-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;}',
      '.cxhp-title{font-size:22px;font-weight:600;margin:0 0 6px;}',
      '.cxhp-sub{font-size:13px;color:var(--dsw-alias-label-secondary);margin:0;}',
      '.cxhp-btn{font:inherit;font-size:13px;padding:7px 14px;border-radius:8px;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);cursor:pointer;}',
      '.cxhp-btn:hover{border-color:var(--dsw-alias-brand-primary);}',
      '.cxhp-btn:disabled{opacity:.55;cursor:default;}',
      '.cxhp-btn--active{border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-brand-primary);}',
      '.cxhp-stats{display:flex;gap:10px;margin:20px 0 14px;flex-wrap:wrap;}',
      '.cxhp-stat{padding:10px 16px;border:1px solid var(--dsw-alias-border-l1);border-radius:10px;background:var(--dsw-alias-bg-layer-1);min-width:120px;}',
      '.cxhp-stat-num{font-size:20px;font-weight:600;}',
      '.cxhp-stat-label{font-size:12px;color:var(--dsw-alias-label-secondary);margin-left:6px;}',
      '.cxhp-meta{font-size:12px;color:var(--dsw-alias-label-secondary);margin:0 0 18px;line-height:1.7;}',
      '.cxhp-meta-warn{color:var(--dsw-alias-state-warn-primary);margin-left:8px;}',
      '.cxhp-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:18px;}',
      '.cxhp-search{font:inherit;font-size:13px;padding:7px 12px;border-radius:8px;border:1px solid var(--dsw-alias-border-l1);background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);min-width:220px;}',
      '.cxhp-search:focus{outline:none;border-color:var(--dsw-alias-brand-primary);}',
      '.cxhp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px;}',
      '.cxhp-card{display:block;text-decoration:none;color:inherit;background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:12px;padding:16px;transition:border-color .15s ease,transform .15s ease;}',
      '.cxhp-card:hover{border-color:var(--dsw-alias-brand-primary);transform:translateY(-2px);}',
      '.cxhp-card--nolink{opacity:.72;cursor:default;}',
      '.cxhp-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;}',
      '.cxhp-course{font-size:12px;color:var(--dsw-alias-label-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
      '.cxhp-badge{flex:none;font-size:12px;padding:3px 9px;border-radius:999px;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-2);}',
      '.cxhp-badge--pending{color:var(--dsw-alias-state-error-primary);border-color:var(--dsw-alias-state-error-primary);}',
      '.cxhp-badge--done{color:var(--dsw-alias-state-success-primary);border-color:var(--dsw-alias-state-success-primary);}',
      '.cxhp-name{font-size:15px;font-weight:600;line-height:1.45;margin:0 0 12px;word-break:break-word;}',
      '.cxhp-dl{font-size:13px;color:var(--dsw-alias-label-secondary);margin:0 0 6px;}',
      '.cxhp-remain{font-size:12px;color:var(--dsw-alias-state-warn-primary);margin:0 0 10px;}',
      '.cxhp-open{font-size:12px;color:var(--dsw-alias-brand-primary);}',
      '.cxhp-empty{padding:48px 16px;text-align:center;color:var(--dsw-alias-label-secondary);font-size:14px;}',
    ].join('');

    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register(NS, { zh: zh, en: en }), 'chaoxing-homework: dictionaries');
        const t = ctx.locale.bind(NS);

        function Icon(props) {
          const size = props.size || 20;
          return h('svg', {
            viewBox: '0 0 24 24', width: size, height: size, fill: 'none',
            stroke: 'currentColor', strokeWidth: '1.7', strokeLinecap: 'round',
            strokeLinejoin: 'round', 'aria-hidden': true,
            style: { color: props.active ? 'var(--dsw-alias-brand-primary)' : 'var(--dsw-alias-label-secondary)', display: 'block' },
          },
            h('rect', { x: '3', y: '4', width: '18', height: '16', rx: '2' }),
            h('path', { d: 'M7 9h10M7 13h10M7 17h6' }),
            h('path', { d: 'M15 16.5l1.6 1.6L20 14.5' })
          );
        }

        function useHomework() {
          const [state, setState] = React.useState({ loading: true, data: null, error: null });
          const reload = React.useCallback(() => {
            setState((s) => ({ loading: true, data: s.data, error: null }));
            fetch('/api/chaoxing.homework', { cache: 'no-store' })
              .then((r) => r.json())
              .then((j) => setState({ loading: false, data: j, error: null }))
              .catch((e) => setState({ loading: false, data: null, error: String(e) }));
          }, []);
          React.useEffect(() => {
            reload();
            const id = setInterval(reload, 60000);
            return () => clearInterval(id);
          }, [reload]);
          return { state: state, reload: reload };
        }

        function Card(props) {
          const it = props.item;
          const badgeText = it.submitted
            ? (it.status === '待批阅' ? t('status.awaiting') : t('status.submitted'))
            : (it.status === '未交' ? t('status.pending') : t('status.other'));
          let dl;
          if (it.closed) dl = t('deadline.closed');
          else if (it.deadlineSource === 'semester_end') dl = t('deadline.semester') + (it.deadlineFull ? ' (' + it.deadlineFull + ')' : '');
          else if (it.deadline) dl = t('deadline.label') + ' ' + it.deadline;
          else dl = t('deadline.unknown');
          const inner = h('div', null,
            h('div', { className: 'cxhp-card-top' },
              h('span', { className: 'cxhp-course', title: it.course }, it.course || '—'),
              h('span', { className: 'cxhp-badge ' + (it.submitted ? 'cxhp-badge--done' : 'cxhp-badge--pending') }, badgeText)
            ),
            h('p', { className: 'cxhp-name' }, it.name),
            h('p', { className: 'cxhp-dl' }, dl),
            it.remainText ? h('p', { className: 'cxhp-remain' }, it.remainText) : null,
            h('span', { className: 'cxhp-open' }, it.taskUrl ? t('open') + ' ↗' : t('no.link'))
          );
          if (it.taskUrl) {
            return h('a', {
              className: 'cxhp-card', href: it.taskUrl, target: '_blank',
              rel: 'noopener noreferrer', title: t('open'),
            }, inner);
          }
          return h('div', { className: 'cxhp-card cxhp-card--nolink', title: t('no.link') }, inner);
        }

        function Page() {
          const hw = useHomework();
          const [filter, setFilter] = React.useState('all');
          const [query, setQuery] = React.useState('');
          const data = hw.state.data;
          const items = data && data.ok ? (data.items || []) : [];
          const pending = items.filter((it) => !it.submitted).length;
          const submitted = items.length - pending;
          const stale = data && data.checkedAt && (Date.now() - new Date(data.checkedAt).getTime() > 26 * 3600 * 1000);
          const q = query.trim().toLowerCase();
          const shown = items.filter((it) => {
            if (filter === 'pending' && it.submitted) return false;
            if (filter === 'submitted' && !it.submitted) return false;
            if (q && (it.course + ' ' + it.name).toLowerCase().indexOf(q) < 0) return false;
            return true;
          }).sort((a, b) => {
            if (a.submitted !== b.submitted) return a.submitted ? 1 : -1;
            return String(a.deadline || '9999').localeCompare(String(b.deadline || '9999'));
          });

          function stat(num, label) {
            return h('div', { className: 'cxhp-stat' },
              h('span', { className: 'cxhp-stat-num' }, String(num)),
              h('span', { className: 'cxhp-stat-label' }, label)
            );
          }
          function filterButton(id, label) {
            return h('button', {
              className: 'cxhp-btn' + (filter === id ? ' cxhp-btn--active' : ''),
              onClick: () => setFilter(id),
            }, label);
          }

          let body;
          if (hw.state.loading && !data) body = h('div', { className: 'cxhp-empty' }, t('loading'));
          else if (hw.state.error) body = h('div', { className: 'cxhp-empty' }, t('error') + ': ' + hw.state.error);
          else if (!data || !data.ok) body = h('div', { className: 'cxhp-empty' }, (data && data.message) ? data.message : t('empty.none'));
          else if (items.length === 0) body = h('div', { className: 'cxhp-empty' }, t('empty.none'));
          else if (shown.length === 0) body = h('div', { className: 'cxhp-empty' }, t('empty.filter'));
          else body = h('div', { className: 'cxhp-grid' }, shown.map((it, i) => h(Card, { key: it.course + '/' + it.name + '/' + i, item: it })));

          return h('div', { className: 'cxhp-page' },
            h('style', null, CSS),
            h('div', { className: 'cxhp-head' },
              h('div', null,
                h('h1', { className: 'cxhp-title' }, t('page.title')),
                h('p', { className: 'cxhp-sub' }, t('page.subtitle'))
              ),
              h('button', {
                className: 'cxhp-btn', onClick: hw.reload, disabled: hw.state.loading,
              }, hw.state.loading ? t('refreshing') : t('refresh'))
            ),
            h('div', { className: 'cxhp-stats' },
              stat(items.length, t('stat.all')),
              stat(pending, t('stat.pending')),
              stat(submitted, t('stat.submitted'))
            ),
            h('p', { className: 'cxhp-meta' },
              data && data.checkedAt ? t('scan.at') + ' ' + new Date(data.checkedAt).toLocaleString('zh-CN') : '',
              stale ? h('span', { className: 'cxhp-meta-warn' }, t('scan.stale')) : null,
              data && data.source ? h('span', null, '　' + t('source') + ': ' + data.source.path) : null
            ),
            h('div', { className: 'cxhp-tools' },
              filterButton('all', t('filter.all')),
              filterButton('pending', t('filter.pending')),
              filterButton('submitted', t('filter.submitted')),
              h('input', {
                className: 'cxhp-search', type: 'search', placeholder: t('search'),
                value: query, onChange: (e) => setQuery(e.target.value),
              })
            ),
            body
          );
        }

        ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
          name: 'sidebar.panellist',
          id: PANEL_ID,
          order: 11,
          locale: NS,
          label: () => t('panel'),
        }, Icon));

        ctx.slots.inject('main', () => ctx.slots.register({
          name: 'main',
          key: PANEL_ID,
          locale: NS,
        }, Page));
      },
    };
  },
});
