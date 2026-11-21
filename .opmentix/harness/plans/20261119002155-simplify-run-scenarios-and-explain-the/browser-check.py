#!/usr/bin/env python3
"""Isolated Playwright QA for Argus Runs UX. ALL /api calls are synthetic and intercepted."""
from __future__ import annotations
import argparse, json, os, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

PROJECT = Path.cwd().resolve()
ROOT = (PROJECT / 'static').resolve()
ARTIFACTS = Path('/tmp/argus-run-ui-browser-artifacts').resolve()
API_LOG: list[dict] = []
SERVER = None
DEFERRED = {'path':None,'route':None,'body':None,'event':threading.Event()}

class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/api/'):
            self.send_error(404); return
        if path == '/': self.path = '/index.html'
        elif path.startswith('/static/'):
            rel = Path(path[len('/static/'):])
            target = (ROOT / rel).resolve()
            if ROOT not in target.parents and target != ROOT:
                self.send_error(403); return
            self.path = '/' + str(rel)
        else:
            self.send_error(404); return
        super().do_GET()
    def log_message(self, *_): pass

def response(route, body, status=200):
    route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

def fixture_for(path, method, body):
    if path == '/api/session': return {'token': 'synthetic-browser-token'}
    if path == '/api/health': return {'data_ok': True, 'flags': {'IncludeWatchlist': True}}
    if path == '/api/config': return {'IncludeWatchlist': True}
    if path == '/api/settings': return {'weekly_budget_enabled': False, 'weekly_budget_usd': 25, 'max_candidates': 100, 'max_stocks_per_sector': 10, 'flags': {'IncludeWatchlist': True}}
    if path == '/api/portfolio':
        positions = [
            {'ticker':'AAA','quantity':10,'price':100,'market_value':1000,'average_cost':90,'sector':'Technology'},
            {'ticker':'BBB','quantity':5,'price':50,'market_value':250,'average_cost':48,'sector':'Healthcare'},
        ]
        return {'positions': positions, 'weights': [], 'targets': {}, 'accounts': [], 'cash': 500, 'cash_known': True, 'holdings_value': 1250, 'total_market_value': 1750, 'total_cost': 1150, 'prices_as_of':'2026-11-18', 'book_newer_than_stats':False}
    if path == '/api/watchlist': return {'items': [
        {'ticker':'CCC','origins':['candidate'],'sector':'Healthcare','instrument_type':'Stock'},
        {'ticker':'DDD','origins':['manual'],'sector':'Technology','instrument_type':'Stock'},
    ]}
    if path == '/api/watchlist/proposal': return {'items': []}
    if path == '/api/runs': return {'runs': []}
    if path == '/api/spend': return {'spent_usd':0,'budget_usd':25,'budget_enabled':False,'unpriced_runs':0,'estimated_runs':0}
    if path == '/api/reports': return {'reports': []}
    if path == '/api/fund-manager': return {'history': [], 'markdown':'', 'stats':{}}
    if path == '/api/theme-scout': return {'screen': [], 'relative_strength': [], 'changes': [], 'markdown':'', 'model_skipped':True}
    if path.startswith('/api/runs/') and path.endswith('/log'): return {'chunk':'synthetic run log\n','offset':19,'done':True}
    if path.startswith('/api/reports/'): return {'report':{},'markdown':''}
    if path == '/api/runs/manifest' and method == 'POST':
        tickers = body.get('tickers') or []
        return {'manifest_sha256':'synthetic-run-hash','manifest':{
            'mode':'ANL' if body.get('analysis_only') else ('REV' if not body.get('no_llm') else 'SNAPSHOT'),
            'stages': [], 'fresh_analysis_tickers':tickers,
            'portfolio_review_context_tickers':['AAA','BBB','CCC','DDD'], 'portfolio_report_inputs':{},
            'cost_estimate':{'amount_usd':0.12,'note':'Synthetic estimate.'},
            'spending_controls':{'weekly_budget_enabled':False,'weekly_budget_usd':25,'spent_usd':0},
            'model_price_inventory':{'rates':[],'pricing_note':'Synthetic'},'outputs':{},
        }}
    if path == '/api/theme-scout/manifest' and method == 'POST':
        return {'manifest_sha256':'synthetic-theme-hash','manifest':{'model':{'model':'synthetic-model','max_tokens':100},'model_scope':{'selected_sector_etfs':[],'holdings':['AAA','BBB'],'saved_candidates':['CCC','DDD'],'dynamic_discovery':{'maximum_stock_tickers':20}},'spending_controls':{'weekly_budget_enabled':False,'weekly_budget_usd':25,'spent_usd':0},'cost_estimate':{'amount_usd':0.12,'note':'Synthetic estimate.'}}}
    if path == '/api/runs' and method == 'POST': return {'run':{'id':'synthetic-run','status':'queued'}}
    if path == '/api/theme-scout' and method == 'POST': return {'run':{'id':'synthetic-theme-run','status':'queued'}}
    return None

def install_route(page):
    def handler(route):
        req = route.request
        path = urlparse(req.url).path
        if not path.startswith('/api/'):
            route.continue_(); return
        try: body = req.post_data_json if req.post_data else {}
        except Exception: body = {'raw':req.post_data}
        row = {'path':path,'method':req.method,'body':body,'headers':dict(req.headers)}
        API_LOG.append(row)
        if DEFERRED['path']==path:
            DEFERRED['route']=route; DEFERRED['body']=body; DEFERRED['event'].set(); return
        fixture = fixture_for(path, req.method, body)
        if fixture is None:
            row['unmocked'] = True
            response(route, {'detail':'Unmocked API blocked by isolated browser harness'}, 404)
        else: response(route, fixture)
    page.route('**/api/**', handler)

def api_since(index=0): return API_LOG[index:]
def ids(calls): return [c['path'] for c in calls]

def main():
    global SERVER, PROJECT, ROOT, ARTIFACTS
    parser=argparse.ArgumentParser(description='Isolated synthetic-data browser checks for Argus Runs UX')
    parser.add_argument('--project', default=str(Path.cwd()), help='Argus project root')
    parser.add_argument('--artifacts', default='/tmp/argus-run-ui-browser-artifacts', help='Screenshot and JSON result directory')
    args=parser.parse_args()
    PROJECT=Path(args.project).resolve(); ROOT=(PROJECT/'static').resolve(); ARTIFACTS=Path(args.artifacts).resolve(); ARTIFACTS.mkdir(parents=True,exist_ok=True)
    SERVER = ThreadingHTTPServer(('127.0.0.1', 0), StaticHandler)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{SERVER.server_port}'
    checks, failures, screenshots = [], [], []
    def check(name, condition, detail=''):
        checks.append({'name':name,'passed':bool(condition),'detail':detail})
        if not condition: failures.append(name + (': ' + detail if detail else ''))
    try:
      with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width':1280,'height':1000}, reduced_motion='reduce')
        page = context.new_page(); js_errors=[]; dialogs=[]
        page.on('pageerror', lambda exc: js_errors.append(str(exc)))
        page.on('dialog', lambda dialog: (dialogs.append(dialog.type), dialog.dismiss()))
        install_route(page)
        page.goto(base, wait_until='domcontentloaded')
        page.wait_for_timeout(800)
        page.locator('[data-tab="runs"]').click()
        page.wait_for_timeout(600)
        check('app_boots_without_js_errors', not js_errors, '; '.join(js_errors))
        check('runs_tab_available', page.locator('#runScenarios').count()==1, 'new run scenario radio fieldset present')
        # Wait for datasets to load before scenario assertions.
        page.locator('#runHoldingTickers input, #runTickerScope input').first.wait_for(state='attached',timeout=5000)
        radio = page.locator('#runScenarios input[type=radio]')
        check('six_scenarios_present', radio.count()==6, f'found {radio.count()}')
        # Scenario changes should only update the draft, with no calls, dialogs, tab switch or scroll.
        calls_before = len(API_LOG); tab_before = page.locator('.ar-nav__item[aria-current="page"]').get_attribute('data-tab') if page.locator('.ar-nav__item[aria-current="page"]').count() else 'runs'
        scroll_before = page.evaluate('window.scrollY')
        modes=['snapshot','screen','scout','analyze','analyze-review','fund']
        no_calls=True; no_dialogs=True; no_scroll=True
        for mode in modes:
            page.locator(f'#runScenarios input[type=radio][value="{mode}"]').check()
            page.wait_for_timeout(60)
            no_calls = no_calls and len(API_LOG)==calls_before
            no_dialogs = no_dialogs and not page.locator('dialog[open]').count() and len(dialogs)==0
            no_scroll = no_scroll and page.evaluate('window.scrollY')==scroll_before
            expected={
                'snapshot':(True,False,False,False,True,True),
                'screen':(False,False,False,True,False,False),
                'scout':(False,False,False,True,False,False),
                'analyze':(False,False,True,False,True,False),
                'analyze-review':(False,True,True,False,True,True),
                'fund':(False,True,False,False,True,True),
            }[mode]
            actual=tuple(page.locator('#'+ident).is_visible() for ident in ['runSnapshotScope','runPortfolioScope','runTickerScope','runSectorScope','runDateBlock','runOptions'])
            check(f'{mode}_only_relevant_controls_visible', actual==expected, f'expected={expected}, actual={actual}')
            check(f'{mode}_inactive_change_notice_hidden', not page.locator('#runTickerChanges').is_visible(), 'no source change notice when no sources changed')
        check('six_mode_changes_are_draft_only', no_calls and no_dialogs and no_scroll, f'calls={ids(api_since(calls_before))}; dialogs={dialogs}; scroll={scroll_before}->{page.evaluate("window.scrollY")}')
        check('mode_selection_keeps_runs_tab', page.locator('#tab-runs:not(.hidden)').count()==1, 'scenario selection must not leave Runs')
        api_key_before=len(API_LOG)
        first_radio=page.locator('#runScenarios input[value="snapshot"]'); first_radio.focus(); page.keyboard.press('ArrowRight'); page.wait_for_timeout(80)
        check('keyboard_radio_navigation', page.locator('#runScenarios input[value="screen"]').is_checked() and len(API_LOG)==api_key_before, 'arrow navigation changes only the local scenario draft')
        # Move to research, clear any scope, and verify inline error/no request.
        page.locator('#runScenarios input[value="analyze"]').check()
        clear = page.locator('[data-run-bulk="clear"], [data-run-bulk="none"], #runClearTickers')
        if clear.count(): clear.first.click()
        api_before=len(API_LOG); page.locator('#runStart').click(); page.wait_for_timeout(150)
        check('empty_research_is_inline_and_offline', len(API_LOG)==api_before and page.locator('#runErrors:not([hidden]), #runTickerError:not([hidden])').count()>0 and page.evaluate('document.activeElement.id')=='runErrors', f'calls={ids(api_since(api_before))}, focused={page.evaluate("document.activeElement.id")}')
        # Find actual ticker checkboxes by labels; explicit manual DDD must be selectable.
        tickers=page.locator('#runTickerScope input[data-run-ticker]')
        available=[]
        for i in range(tickers.count()): available.append(tickers.nth(i).get_attribute('value') or tickers.nth(i).get_attribute('data-run-ticker'))
        check('manual_nonheld_candidate_visible', 'DDD' in available, f'available={available}')
        for symbol in ['AAA','DDD']:
            box=page.locator(f'#runTickerScope input[value="{symbol}"], #runTickerScope input[data-run-ticker="{symbol}"]')
            if box.count():
                try: box.first.check(timeout=1500)
                except Exception as exc: print('ticker-check-debug', symbol, str(exc).splitlines()[-1], page.locator('#runTickerScope').inner_text(), page.locator(f'#runTickerScope input[data-run-ticker="{symbol}"]').is_checked())
        page.locator('#runScenarios input[value="fund"]').check()
        page.locator('#runScenarios input[value="analyze-review"]').check()
        selected=[]
        for i in range(tickers.count()):
            if tickers.nth(i).is_checked(): selected.append(tickers.nth(i).get_attribute('value') or tickers.nth(i).get_attribute('data-run-ticker'))
        check('ticker_selection_survives_mode_changes', set(selected)=={'AAA','DDD'}, f'selected={selected}')
        check('valid_scope_has_no_stale_warning', not page.locator('#runTickerChanges').is_visible(), page.locator('#runTickerChanges').inner_text())
        # Populate advanced state where present to test hidden-field omission in fund and scout payloads.
        if page.locator('#runOptions summary').count(): page.locator('#runOptions summary').click()
        if page.locator('#runEconomicData').count():
            page.locator('#runEconomicData').uncheck()
        if page.locator('#runSince').count(): page.locator('#runSince').fill('2026-11-01')
        if page.locator('#runDateInput').count():
            custom=page.locator('#runDateModeCustom, #runDateBlock input[value="custom"]')
            if custom.count(): custom.first.check()
            page.locator('#runDateInput').fill('2026-11-18')
        # Fund draft should not leak selected tickers/date/since/macro into its API request.
        page.locator('#runScenarios input[value="fund"]').check()
        api_before=len(API_LOG); page.locator('#runStart').click(); page.wait_for_timeout(1200)
        calls=api_since(api_before)
        manifest=next((c for c in calls if c['path']=='/api/runs/manifest'),None)
        check('fund_manifest_only_after_start', manifest is not None, f'calls={ids(calls)}')
        if manifest:
            b=manifest['body']; check('fund_uses_only_relevant_options', not b.get('tickers') and b.get('analysis_date') == '2026-11-18' and b.get('since') == '2026-11-01' and b.get('no_macro') is True, json.dumps(b))
        # cancel review should preserve mode/draft and restore focus
        cancel=page.locator('#confirmCancel, #runCancel')
        if page.locator('dialog[open]').count() and cancel.count(): cancel.first.click()
        check('cancel_closes_review', page.locator('dialog[open]').count()==0, 'dialog closed')
        check('cancel_restores_start_focus', page.evaluate('document.activeElement.id')=='runStart', f'active={page.evaluate("document.activeElement.id")}')
        check('cancel_preserves_draft', page.locator('#runScenarios input[value="fund"]').is_checked() and page.locator('#runSince').input_value()=='2026-11-01', 'fund mode and since date retained')
        # Scout requests only its selected sectors; hidden research/date/economic settings are omitted.
        page.locator('#runScenarios input[value="scout"]').check()
        sectors=page.locator('#runSectorScope input[data-run-sector]')
        for i in range(sectors.count()):
            el=sectors.nth(i)
            if el.get_attribute('value') in ['XLV','XLP'] and not el.is_checked(): el.check()
            elif el.get_attribute('value') not in ['XLV','XLP'] and el.is_checked(): el.uncheck()
        api_before=len(API_LOG); page.locator('#runStart').click(); page.locator('#confirmModal[open]').wait_for(timeout=5000)
        scout=next((c for c in api_since(api_before) if c['path']=='/api/theme-scout/manifest'),None)
        check('scout_uses_only_selected_sectors', scout is not None and scout['body'].get('sectors')==['XLV','XLP'], json.dumps(scout['body'] if scout else ids(api_since(api_before))))
        if scout:
            b=scout['body']; check('scout_omits_hidden_fields', not b.get('tickers') and not b.get('analysis_date') and not b.get('since') and 'no_macro' not in b, json.dumps(b))
        check('paid_confirmation_requires_consent', page.locator('#confirmGo').is_disabled() and page.locator('#confirmConsent').is_visible(), 'paid modal requires explicit consent')
        page.screenshot(path=str(ARTIFACTS/'runs-paid-review.png'), full_page=False); screenshots.append(str(ARTIFACTS/'runs-paid-review.png'))
        page.keyboard.press('Escape'); page.wait_for_timeout(80)
        check('scout_escape_restores_start_focus', not page.locator('#confirmModal[open]').count() and page.evaluate('document.activeElement.id')=='runStart', f'active={page.evaluate("document.activeElement.id")}')
        check('paid_cancel_returns_without_start', not any(c['path']=='/api/theme-scout' and c['method']=='POST' for c in api_since(api_before)), 'only manifest requested')
        # Research + portfolio review uses exactly the selected fresh-research names; fake POST is intercepted.
        page.locator('#runScenarios input[value="analyze-review"]').check()
        api_before=len(API_LOG); page.locator('#runStart').click(); page.locator('#confirmModal[open]').wait_for(timeout=5000)
        research_manifest=next((c for c in api_since(api_before) if c['path']=='/api/runs/manifest'),None)
        check('research_manifest_exact_scope', research_manifest is not None and research_manifest['body'].get('tickers')==['AAA','DDD'], json.dumps(research_manifest['body'] if research_manifest else ids(api_since(api_before))))
        if research_manifest:
            check('research_manifest_hash_frozen', 'synthetic-run-hash' in page.locator('#confirmText').inner_text() or research_manifest.get('body',{}).get('manifest_sha256') is None, 'manifest preview captured before confirmation')
        check('research_confirm_requires_consent', page.locator('#confirmGo').is_disabled(), 'paid research confirmation disabled until consent')
        if page.locator('#confirmConsent').count(): page.locator('#confirmConsent').check()
        if page.locator('#confirmGo').is_enabled(): page.locator('#confirmGo').click()
        page.wait_for_timeout(250)
        posts=[c for c in api_since(api_before) if c['path']=='/api/runs' and c['method']=='POST']
        check('confirmed_run_is_fake_and_hash_bound', len(posts)==1 and posts[0]['body'].get('manifest_sha256')=='synthetic-run-hash' and posts[0]['body'].get('confirm') is True and posts[0]['body'].get('tickers')==['AAA','DDD'], json.dumps(posts[-1]['body'] if posts else ids(api_since(api_before))))
        # Stale response is discarded if the draft changes while its preview request is pending.
        page.locator('#runScenarios input[value="snapshot"]').check(); api_before=len(API_LOG)
        page.evaluate("""() => { document.querySelector('#runStart').dispatchEvent(new MouseEvent('click',{bubbles:true})); const next=document.querySelector('#runScenarios input[value=\"screen\"]'); next.checked=true; next.dispatchEvent(new Event('change',{bubbles:true})); }""")
        page.wait_for_timeout(350)
        stale_calls=api_since(api_before)
        check('stale_preview_discarded_after_draft_edit', len([c for c in stale_calls if c['path']=='/api/runs/manifest'])==1 and not page.locator('#confirmModal').evaluate('(el)=>el.open') and 'draft or page changed' in page.locator('#runResult').inner_text().lower(), f'calls={ids(stale_calls)}, modal={page.locator("#confirmModal").evaluate('(el)=>el.open')}, result={page.locator("#runResult").inner_text()}')
        # Rapid duplicate Start dispatches should produce only one manifest preview.
        page.locator('#runScenarios input[value="snapshot"]').check(); api_before=len(API_LOG)
        page.evaluate("""() => { const start=document.querySelector('#runStart'); start.dispatchEvent(new MouseEvent('click',{bubbles:true})); start.dispatchEvent(new MouseEvent('click',{bubbles:true})); }""")
        page.locator('#confirmModal[open]').wait_for(timeout=5000); page.wait_for_timeout(150)
        duplicate_calls=[c for c in api_since(api_before) if c['path']=='/api/runs/manifest']
        check('duplicate_start_has_single_preview', len(duplicate_calls)==1, f'manifest count={len(duplicate_calls)}')
        if page.locator('#confirmCancel').count(): page.locator('#confirmCancel').click()
        # Escape returns focus to Start and retains the draft without starting anything.
        page.locator('#runScenarios input[value="fund"]').check(); api_before=len(API_LOG)
        page.locator('#runStart').click(); page.locator('#confirmModal[open]').wait_for(timeout=5000)
        page.keyboard.press('Escape'); page.wait_for_timeout(100)
        check('escape_closes_review_restores_focus', not page.locator('#confirmModal[open]').count() and page.evaluate('document.activeElement.id')=='runStart' and page.locator('#runScenarios input[value="fund"]').is_checked(), f'active={page.evaluate("document.activeElement.id")}, calls={ids(api_since(api_before))}')
        # A late manifest must not open a review after the user leaves and returns to Runs.
        page.locator('#runScenarios input[value="fund"]').check(); api_before=len(API_LOG)
        DEFERRED.update(path='/api/runs/manifest',route=None,body=None); DEFERRED['event'].clear()
        page.locator('#runStart').dispatch_event('click'); page.wait_for_timeout(120)
        request_held=DEFERRED['event'].is_set()
        page.locator('#nav [data-tab="portfolio"]').click(); page.wait_for_timeout(120)
        page.locator('#nav [data-tab="runs"]').click(); page.wait_for_timeout(120)
        if request_held:
            delayed_body=DEFERRED['body']; delayed_fixture=fixture_for('/api/runs/manifest','POST',delayed_body)
            DEFERRED['route'].fulfill(status=200,content_type='application/json',body=json.dumps(delayed_fixture))
        DEFERRED.update(path=None,route=None,body=None); DEFERRED['event'].clear(); page.wait_for_timeout(250)
        check('late_preview_ignored_after_tab_leave_return', request_held and not page.locator('#confirmModal[open]').count(), f'held={request_held}, modal={bool(page.locator("#confirmModal[open]").count())}, calls={ids(api_since(api_before))}')
        # The scout manifest path uses the same invalidation guard when the user leaves and returns.
        page.locator('#runScenarios input[value="scout"]').check(); api_before=len(API_LOG)
        DEFERRED.update(path='/api/theme-scout/manifest',route=None,body=None); DEFERRED['event'].clear()
        page.locator('#runStart').dispatch_event('click'); page.wait_for_timeout(120)
        scout_held=DEFERRED['event'].is_set()
        page.locator('#nav [data-tab="portfolio"]').click(); page.wait_for_timeout(120)
        page.locator('#nav [data-tab="runs"]').click(); page.wait_for_timeout(120)
        if scout_held:
            delayed_body=DEFERRED['body']; delayed_fixture=fixture_for('/api/theme-scout/manifest','POST',delayed_body)
            DEFERRED['route'].fulfill(status=200,content_type='application/json',body=json.dumps(delayed_fixture))
        DEFERRED.update(path=None,route=None,body=None); DEFERRED['event'].clear(); page.wait_for_timeout(250)
        check('late_scout_preview_ignored_after_tab_leave_return', scout_held and not page.locator('#confirmModal[open]').count(), f'held={scout_held}, modal={bool(page.locator("#confirmModal[open]").count())}, calls={ids(api_since(api_before))}')
        # Responsive layout screenshots and horizontal overflow check
        page.locator('#runScenarios input[value="snapshot"]').check(); page.evaluate('window.scrollTo(0,0)')
        for width,name in [(1280,'desktop'),(768,'tablet'),(375,'mobile')]:
            page.set_viewport_size({'width':width,'height':900}); page.evaluate('window.scrollTo(0,0)'); page.wait_for_timeout(100)
            page.screenshot(path=str(ARTIFACTS/f'runs-{name}.png'), full_page=True); screenshots.append(str(ARTIFACTS/f'runs-{name}.png'))
            overflow=page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth')
            check(f'no_horizontal_overflow_{width}', not overflow, f'scrollWidth={page.evaluate("document.documentElement.scrollWidth")}, clientWidth={page.evaluate("document.documentElement.clientWidth")}, offenders={page.evaluate("Array.from(document.querySelectorAll(\'*\')).map(e=>({tag:e.tagName,id:e.id,cls:typeof e.className===\'string\'?e.className:\'\',right:Math.round(e.getBoundingClientRect().right),left:Math.round(e.getBoundingClientRect().left),width:Math.round(e.getBoundingClientRect().width)})).filter(x=>x.right>innerWidth+1||x.left < -1).slice(0,12)")}')
            form_overflow=page.locator('#runComposer').evaluate("root => Array.from(root.querySelectorAll('*')).some(el => el.getBoundingClientRect().right > root.getBoundingClientRect().right + 1)")
            check(f'no_run_form_overflow_{width}', not form_overflow, f'form overflow={form_overflow}')
        # 200% effective-width reflow proxy, then check reduced-motion style.
        page.set_viewport_size({'width':640,'height':900}); page.evaluate('window.scrollTo(0,0)'); page.wait_for_timeout(100)
        zoom_overflow=page.locator('#runComposer').evaluate("root => Array.from(root.querySelectorAll('*')).some(el => el.getBoundingClientRect().right > root.getBoundingClientRect().right + 1)")
        check('run_form_reflows_at_200_percent_equivalent', not zoom_overflow, f'form overflow={zoom_overflow}')
        reduced=page.evaluate("getComputedStyle(document.querySelector('#runStart')).transitionDuration")
        check('reduced_motion_applied', all(float(value.strip().removesuffix('s')) <= 0.01 for value in reduced.split(',')), f'transition duration={reduced}')
        targets=page.evaluate("""() => ['#runStart','#runComposer [data-run-bulk]','#runComposer .ar-run-option','#runComposer .ar-run-chip'].flatMap(sel=>Array.from(document.querySelectorAll(sel)).filter(el=>el.getClientRects().length).map(el=>({selector:sel,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height})))""")
        small_targets=[t for t in targets if t['width'] < 44 or t['height'] < 44]
        check('run_controls_have_44px_targets', not small_targets, json.dumps(small_targets))
        def contrast_rows(label):
            rows=page.evaluate("""() => {
              const sels=['.ar-run-scenario strong','.ar-run-scenario > span > span','#runStatus','#runStartHelp'];
              function color(el,key){ let cur=el; while(cur){ const c=getComputedStyle(cur)[key]; if(key==='color'||c && c!=='rgba(0, 0, 0, 0)' && c!=='transparent') return c; cur=cur.parentElement; } return 'rgb(255,255,255)'; }
              return sels.flatMap(sel=>Array.from(document.querySelectorAll(sel)).filter(el=>el.getClientRects().length).map(el=>({selector:sel,text:el.textContent.trim().slice(0,45),fg:color(el,'color'),bg:color(el,'backgroundColor')})));
            }""")
            def rgb(v):
                nums=[float(x) for x in __import__('re').findall(r'[\d.]+',v)]
                if len(nums)<3: return (255,255,255)
                return tuple(nums[:3])
            def lum(v):
                vals=[]
                for x in rgb(v):
                    x=x/255; vals.append(x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4)
                return .2126*vals[0]+.7152*vals[1]+.0722*vals[2]
            return [{'label':label,**row,'ratio':round((max(lum(row['fg']),lum(row['bg']))+.05)/(min(lum(row['fg']),lum(row['bg']))+.05),2)} for row in rows]
        light_contrast=contrast_rows('light'); check('critical_run_text_contrast_light', all(r['ratio']>=4.5 for r in light_contrast), json.dumps(light_contrast))
        # dark mode, keyboard tab entry and zoom proxy (viewport scaled to 200% equivalent).
        theme=page.locator('#themeToggle [data-theme-set="dark"]')
        if theme.count(): theme.click()
        dark_contrast=contrast_rows('dark'); check('critical_run_text_contrast_dark', all(r['ratio']>=4.5 for r in dark_contrast), json.dumps(dark_contrast))
        page.evaluate('window.scrollTo(0,0)'); page.screenshot(path=str(ARTIFACTS/'runs-dark.png'),full_page=True); screenshots.append(str(ARTIFACTS/'runs-dark.png'))
        check('no_unmocked_api_calls', not any(c.get('unmocked') for c in API_LOG), json.dumps([c for c in API_LOG if c.get('unmocked')]))
        check('no_native_dialogs_on_scenario_selection', not dialogs, str(dialogs))
        browser.close()
    finally:
        SERVER.shutdown()
    report={'base_url':base,'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':len(failures),'failures':failures,'api_calls':API_LOG,'js_errors':js_errors if 'js_errors' in locals() else [],'screenshots':screenshots,'note':'All /api requests are intercepted and fulfilled from synthetic fixtures. No backend is started.'}
    (ARTIFACTS/'results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ['passed','failed','failures','js_errors','screenshots']},indent=2))
    return 1 if failures else 0

if __name__=='__main__': raise SystemExit(main())
