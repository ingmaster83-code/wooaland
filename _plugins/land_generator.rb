require 'json'

module Jekyll
  module LText
    module_function

    def hangul_tail?(s)
      c = s.to_s.strip.sub(/[\s\)\]\}\>'"”’.,!?~·\-]+\z/, '')[-1]
      !c.nil? && c.ord >= 0xAC00 && c.ord <= 0xD7A3
    end

    def batchim?(s)
      c = s.to_s.strip.sub(/[\s\)\]\}\>'"”’.,!?~·\-]+\z/, '')[-1]
      return false if c.nil?
      o = c.ord
      (o >= 0xAC00 && o <= 0xD7A3) ? ((o - 0xAC00) % 28 != 0) : false
    end

    def josa(word, with_b, without_b)
      return "#{word}#{with_b}(#{without_b})" unless hangul_tail?(word)
      word.to_s + (batchim?(word) ? with_b : without_b)
    end

    def eun_neun(w); josa(w, '은', '는'); end
    def i_ga(w); josa(w, '이', '가'); end

    def fmt(n)
      n.to_i.to_s.reverse.scan(/\d{1,3}/).join(',').reverse
    end

    # 만원 단위 → "12억 3,500만원"
    def man(n)
      n = n.to_f.round
      return '-' if n <= 0
      eok = n / 10_000
      rest = n % 10_000
      if eok.positive?
        rest.zero? ? "#{eok}억원" : "#{eok}억 #{fmt(rest)}만원"
      else
        "#{fmt(n)}만원"
      end
    end

    def py(v)
      v.to_i.positive? ? "#{fmt(v)}만원/평" : '-'
    end

    def pct(v)
      return '-' if v.nil?
      v >= 0 ? "+#{format('%.1f', v)}%" : "#{format('%.1f', v)}%"
    end

    def date(ymd)
      y = ymd.to_i / 10_000
      m = (ymd.to_i / 100) % 100
      d = ymd.to_i % 100
      format('%04d.%02d.%02d', y, m, d)
    end

    def ym(ymd)
      format('%04d.%02d', ymd.to_i / 10_000, (ymd.to_i / 100) % 100)
    end

    def area(a)
      a.to_f == a.to_f.round ? fmt(a.to_f.round) : format('%.1f', a.to_f)
    end

    def chg(cur, prev)
      return nil unless cur && prev && prev.positive? && cur.positive?
      ((cur.to_f / prev - 1) * 100).round(1)
    end
  end

  class LandGenerator < Generator
    safe true
    priority :normal

    KINDS = {
      'land' => { 'name' => '토지', 'short' => '땅값', 'title' => '땅값', 'long' => '토지(땅값) 매매 실거래가', 'tl' => '지목', 'icon' => '🌱', 'basis' => '토지 면적', 'noun' => '토지' },
      'shop' => { 'name' => '상가·사무실', 'short' => '상가', 'title' => '상가 시세', 'long' => '상가·사무실(상업업무용 부동산) 매매 실거래가', 'tl' => '건물용도', 'icon' => '🏬', 'basis' => '건물 면적', 'noun' => '상업업무용 부동산' },
      'factory' => { 'name' => '공장·창고', 'short' => '공장', 'title' => '공장·창고 시세', 'long' => '공장·창고 등 부동산 매매 실거래가', 'tl' => '건물용도', 'icon' => '🏭', 'basis' => '건물 면적', 'noun' => '공장·창고' },
      'house' => { 'name' => '단독·다가구', 'short' => '주택', 'title' => '단독주택 시세', 'long' => '단독·다가구 주택 매매 실거래가', 'tl' => '주택유형', 'icon' => '🏠', 'basis' => '대지 면적', 'noun' => '단독·다가구 주택' }
    }.freeze
    JM_LABEL = { '대' => '대지', '전' => '밭(전)', '답' => '논(답)', '임야' => '임야', '과수원' => '과수원', '잡종지' => '잡종지', '공장용지' => '공장용지', '목장용지' => '목장용지' }.freeze
    DONG_ROWS = 250
    RANK_MIN_SG = 30
    RANK_MIN_DONG = 8

    def generate(site)
      dir = File.join(site.source, '_rawdata')
      meta = JSON.parse(File.read(File.join(dir, 'land_meta.json'), encoding: 'utf-8'))
      recs = []
      Dir.glob(File.join(dir, 'land_*.json')).sort.each do |f|
        next if f.end_with?('land_meta.json')
        recs.concat(JSON.parse(File.read(f, encoding: 'utf-8')))
      end
      latest = LText.date(meta['latest'])
      built = meta['built']
      periods = LandGenerator.periods(built)

      idx = {}                     # [k, do, sg, dong, jm] -> rec
      recs.each { |r| idx[[r['k'], r['do'], r['sg'], r['dong'], r['jm'].to_s]] = r }
      dongs_by_sg = recs.select { |r| r['dong'] != '' }.group_by { |r| [r['k'], r['do'], r['sg']] }
      sg_by_do = recs.select { |r| r['dong'] == '' && !r.key?('jm') }.group_by { |r| [r['k'], r['do']] }
      jm_by_sg = recs.select { |r| r.key?('jm') }.group_by { |r| [r['k'], r['do'], r['sg']] }

      present = KINDS.keys.select { |kk| recs.any? { |r| r['k'] == kk } }     # 수집이 부족한 종류는 데이터가 없으므로 사이트에서 빠진다
      counts = Hash.new(0)
      recs.each do |r|
        k = r['k']
        if r.key?('jm')
          site.pages << JimokPage.new(site, r, latest, periods)
          counts[:jimok] += 1
        elsif r['dong'] != ''
          sg_rec = idx[[k, r['do'], r['sg'], '', '']]
          nb = (dongs_by_sg[[k, r['do'], r['sg']]] || []).reject { |x| x['dong'] == r['dong'] }.sort_by { |x| -x['n'] }.first(10)
          others = KINDS.keys.reject { |x| x == k }.select { |x| idx[[x, r['do'], r['sg'], r['dong'], '']] }
          site.pages << HubPage.new(site, 'dong', r, latest, periods, sg_rec: sg_rec, neighbors: nb, others: others)
          counts[:dong] += 1
        else
          dl = (dongs_by_sg[[k, r['do'], r['sg']]] || []).sort_by { |x| [-x['n'], x['dong']] }
          jl = (jm_by_sg[[k, r['do'], r['sg']]] || []).sort_by { |x| -x['n'] }
          others = KINDS.keys.reject { |x| x == k }.select { |x| idx[[x, r['do'], r['sg'], '', '']] }
          site.pages << HubPage.new(site, 'sg', r, latest, periods, dongs: dl, jimoks: jl, others: others)
          counts[:sg] += 1
        end
      end

      # 시도 허브(종류별): 시군구 집계는 시군구 레코드의 합이 아니라 시군구 목록 표로 보여준다
      present.each do |k|
        by_do = sg_by_do.select { |(kk, _), _| kk == k }
        by_do.each do |(_, d), sgs|
          site.pages << DoHubPage.new(site, k, d, sgs, latest, periods)
          counts[:do] += 1
          pool = (recs.select { |r| r['k'] == k && r['do'] == d && r['dong'] != '' && r['n'] >= RANK_MIN_DONG }).sort_by { |r| -r['med'] }.first(60)
          tops = sgs.flat_map { |s| s['top'].map { |t| t + [s['sg']] } }.sort_by { |t| -t[3] }.first(15)
          site.pages << RankPage.new(site, k, d, sgs.select { |s| s['n'] >= 10 }.sort_by { |s| -s['med'] }, pool, tops, latest)
          counts[:rank] += 1
        end
        all_sg = sg_by_do.select { |(kk, _), _| kk == k }.values.flatten
        nat_tops = all_sg.flat_map { |s| s['top'].map { |t| t + [s['sg'], s['do']] } }.sort_by { |t| -t[3] }.first(20)
        site.pages << RankPage.new(site, k, nil, all_sg.select { |s| s['n'] >= RANK_MIN_SG }.sort_by { |s| -s['med'] }.first(100), [], nat_tops, latest)
        counts[:rank] += 1
        site.pages << KindIndexPage.new(site, k, all_sg, latest, periods)
      end
      site.pages << RankIndexPage.new(site, latest, present)

      stats = {}
      present.each do |k|
        sgs = recs.select { |r| r['k'] == k && r['dong'] == '' && !r.key?('jm') }
        n = sgs.sum { |r| r['n'] }
        stats[k] = { 'n' => LText.fmt(n), 'sg' => sgs.size, 'dong' => recs.count { |r| r['k'] == k && r['dong'] != '' },
                     'top' => sgs.select { |s| s['n'] >= RANK_MIN_SG }.sort_by { |s| -s['med'] }.first(8).map { |s| { 'name' => "#{s['do']} #{s['sg']}", 'url' => "/#{k}/#{s['do']}/#{s['sg']}/", 'med' => LText.py(s['med']), 'n' => LText.fmt(s['n']) } },
                     'busy' => sgs.sort_by { |s| -s['n'] }.first(8).map { |s| { 'name' => "#{s['do']} #{s['sg']}", 'url' => "/#{k}/#{s['do']}/#{s['sg']}/", 'med' => LText.py(s['med']), 'n' => LText.fmt(s['n']) } } }
      end
      site.data['land_stats'] = { 'latest' => latest, 'kinds' => present.map { |k| KINDS[k].merge('k' => k).merge(stats[k]) }, 'pages' => counts.values.sum }

      index = []
      recs.each do |r|
        next if r.key?('jm')
        kind = KINDS[r['k']]
        if r['dong'] != ''
          index << { 'n' => r['dong'], 't' => "#{kind['name']}", 'l' => "#{r['do']} #{r['sg']}", 'u' => "/#{r['k']}/#{r['do']}/#{r['sg']}/#{r['dong']}/" }
        else
          index << { 'n' => r['sg'], 't' => "#{kind['name']}", 'l' => r['do'], 'u' => "/#{r['k']}/#{r['do']}/#{r['sg']}/" }
        end
      end
      pg = PageWithoutAFile.new(site, site.source, '', 'search_index.json')
      pg.content = JSON.generate(index)
      pg.data['layout'] = nil
      pg.data['sitemap'] = false
      site.pages << pg
      Jekyll.logger.info 'LandGenerator:', "동 #{counts[:dong]} / 시군구 #{counts[:sg]} / 지목 #{counts[:jimok]} / 시도 #{counts[:do]} / 랭킹 #{counts[:rank] + 1} (레코드 #{recs.size})"
    end

    # 기간 라벨(가공 기준일 built=YYYYMMDD 에서 1년씩 거슬러 계산)
    def self.periods(built)
      y = built / 10_000
      m = (built / 100) % 100
      lab = lambda do |k|
        e_y, e_m = y - k, m
        s_y, s_m = e_y - 1, e_m + 1
        if s_m > 12
          s_m = 1
          s_y += 1
        end
        "#{format('%04d.%02d', s_y, s_m)}~#{format('%04d.%02d', e_y, e_m)}"
      end
      [lab.call(0), lab.call(1), lab.call(2)]
    end

    def self.win_rows(rec, periods)
      names = ['최근 12개월', '직전 12개월', '그 전 12개월']
      rows = rec['w'].each_with_index.map do |(n, med), i|
        { 'name' => names[i], 'period' => periods[i], 'n' => LText.fmt(n), 'med' => n.positive? ? LText.py(med) : '-' }
      end
      3.times do |i|
        nxt = rec['w'][i + 1]
        cur = rec['w'][i]
        c = nxt && cur[0] >= 3 && nxt[0] >= 3 ? LText.chg(cur[1], nxt[1]) : nil
        rows[i]['chg'] = LText.pct(c)
        rows[i]['up'] = c && c >= 0
      end
      rows
    end

    def self.trade_rows(rec, k)
      rec['r'].map do |ymd, ty, a, a2, amt, py, jb, zone, gbn, dg|
        { 'd' => LText.date(ymd), 'ty' => ty, 'a' => LText.area(a), 'a2' => a2.to_f.positive? ? LText.area(a2) : '-', 'amt' => LText.man(amt), 'py' => LText.py(py), 'jb' => jb, 'zone' => zone, 'gbn' => gbn, 'dg' => dg }
      end
    end

    def self.type_rows(rec, k)
      rec['t'].map { |ty, n, py, a, amt| { 'ty' => k == 'land' ? "#{ty}" : ty, 'n' => LText.fmt(n), 'py' => LText.py(py), 'a' => LText.area(a), 'amt' => LText.man(amt) } }
    end

    def self.url(k, *parts)
      "/#{k}/#{parts.join('/')}/"
    end
  end

  class LBasePage < Page
    def setup(site, dir, layout)
      @site = site
      @base = site.source
      @dir = dir
      @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), "#{layout}.html")
      data['layout'] = layout
    end

    def seo(title, desc)
      data['title'] = title
      data['description'] = desc[0, 155]
    end

    def faq(pairs)
      data['faq'] = pairs.map { |q, a| { 'q' => q, 'a' => a } }
    end

    def f(n)
      LText.fmt(n)
    end
  end

  # ── 시군구·동 허브 ───────────────────────────────────
  class HubPage < LBasePage
    def initialize(site, level, r, latest, periods, sg_rec: nil, neighbors: [], dongs: [], jimoks: [], others: [])
      k = r['k']
      info = LandGenerator::KINDS[k]
      if level == 'dong'
        setup(site, "#{k}/#{r['do']}/#{r['sg']}/#{r['dong']}", 'hub')
        place = "#{r['do']} #{r['sg']} #{r['dong']}"
      else
        setup(site, "#{k}/#{r['do']}/#{r['sg']}", 'hub')
        place = "#{r['do']} #{r['sg']}"
      end
      data['level'] = level
      data['k'] = k
      data['info'] = info
      data['place'] = place
      data['doShort'] = r['do']
      data['sigungu'] = r['sg']
      data['dong'] = r['dong']
      data['latest'] = latest
      data['n'] = f(r['n'])
      data['n12'] = f(r['n12'])
      data['med'] = LText.py(r['med'])
      data['medSqm'] = LText.fmt((r['med'] / 3.3058).round)
      data['mp'] = LText.man(r['mp'])
      data['mx'] = LText.man(r['mx'])
      data['mn'] = LText.man(r['mn'])
      data['avg'] = LText.py(r['avg'])
      data['wRows'] = LandGenerator.win_rows(r, periods)
      cur = r['w'][0]
      pre = r['w'][1]
      c = cur[0] >= 3 && pre[0] >= 3 ? LText.chg(cur[1], pre[1]) : nil
      data['chg'] = LText.pct(c)
      data['hasChg'] = !c.nil?
      data['up'] = c && c >= 0
      data['tRows'] = LandGenerator.type_rows(r, k)
      data['zones'] = r['z'].map { |z, n| { 'z' => z, 'n' => f(n) } }
      data['corp'] = r['b']
      data['unit'] = r['c']
      data['age'] = r['age'].to_i
      data['tRecent'] = LandGenerator.trade_rows(r, k)
      data['top'] = (r['top'] || []).map { |ymd, ty, a, amt, py, dg, jb| { 'd' => LText.date(ymd), 'ty' => ty, 'a' => LText.area(a), 'amt' => LText.man(amt), 'py' => LText.py(py), 'dg' => dg, 'jb' => jb } }
      data['others'] = others.map { |x| { 'name' => LandGenerator::KINDS[x]['name'], 'title' => LandGenerator::KINDS[x]['title'], 'url' => LandGenerator.url(x, *(level == 'dong' ? [r['do'], r['sg'], r['dong']] : [r['do'], r['sg']])) } }
      data['aaptUrl'] = "https://wooaapt.wooahouse.com/region/#{r['do']}/#{r['sg']}/#{level == 'dong' ? "#{r['dong']}/" : ''}"
      data['villaUrl'] = "https://wooavilla.wooahouse.com/region/#{r['do']}/#{r['sg']}/#{level == 'dong' ? "#{r['dong']}/" : ''}"
      data['gongsiUrl'] = "https://wooagongsi.wooahouse.com/region/#{r['do']}/#{r['sg']}/#{level == 'dong' ? "#{r['dong']}/" : ''}"
      data['hakUrl'] = "https://wooahakgun.wooahouse.com/region/#{r['do']}/#{r['sg']}/"
      if sg_rec
        data['vsSg'] = sg_rec['med'].to_i.positive? && r['med'].to_i.positive? ? ((r['med'].to_f / sg_rec['med'] * 100).round) : nil
        data['sgMed'] = LText.py(sg_rec['med'])
      end
      data['neighbors'] = neighbors.map { |x| { 'name' => x['dong'], 'url' => LandGenerator.url(k, x['do'], x['sg'], x['dong']), 'n' => f(x['n']), 'med' => LText.py(x['med']) } }
      data['dongRows'] = dongs.first(LandGenerator::DONG_ROWS).map do |x|
        wc = x['w'][0][0] >= 3 && x['w'][1][0] >= 3 ? LText.chg(x['w'][0][1], x['w'][1][1]) : nil
        { 'name' => x['dong'], 'url' => LandGenerator.url(k, x['do'], x['sg'], x['dong']), 'n' => f(x['n']), 'n12' => f(x['n12']), 'med' => LText.py(x['med']), 'mp' => LText.man(x['mp']), 'chg' => LText.pct(wc), 'up' => wc && wc >= 0 }
      end
      data['nDongs'] = dongs.size
      data['jimoks'] = jimoks.map { |x| { 'label' => LandGenerator::JM_LABEL[x['jm']] || x['jm'], 'url' => "/land-type/#{x['do']}/#{x['sg']}/#{x['jm']}/", 'n' => f(x['n']), 'med' => LText.py(x['med']) } }

      t0 = r['t'].first
      s = +"#{place}에서 최근 36개월 동안 #{info['noun']} #{f(r['n'])}건의 매매가 신고됐고, 이 중 최근 12개월은 #{f(r['n12'])}건입니다. "
      s << "최근 12개월 기준 #{info['basis']} 평당 가격(중앙값)은 #{LText.py(r['med'])}(㎡당 약 #{data['medSqm']}만원), 거래금액 중앙값은 #{LText.man(r['mp'])}입니다. "
      s << "직전 12개월과 비교하면 평당 중앙값이 #{LText.pct(c)} 변동했습니다. " if c
      if t0
        s << "가장 많이 거래된 #{LText.eun_neun(info['tl'])} #{t0[0]}(#{f(t0[1])}건, 평당 #{LText.py(t0[2])})입니다. "
      end
      s << "주요 용도지역은 #{r['z'].first(2).map { |z, _| z }.join('·')}입니다. " unless r['z'].empty?
      s << "거래 상대가 법인인 비율은 #{r['b']}%입니다. " if r['b']
      data['summary'] = s

      cat = info['title']
      seo("#{place} #{cat} - #{info['name']} 실거래가·평당가 #{latest[0, 4]}", "#{place} #{info['long']}. 최근 12개월 평당 #{LText.py(r['med'])}, 거래 #{f(r['n12'])}건. #{info['tl']}별 시세와 최근 거래 내역.")
      pairs = []
      pairs << ["#{place} #{cat}은 평당 얼마인가요?", "최근 12개월 신고된 #{f(r['n12'])}건의 평당 가격 중앙값은 #{LText.py(r['med'])}입니다. 평당가는 거래금액을 #{info['basis']}(평)으로 나눈 값이며, 입지·모양·용도에 따라 개별 물건은 크게 다릅니다."]
      pairs << ['이 자료에서 지번이 일부만 보이는 이유는 무엇인가요?', '국토교통부 실거래가 공개 자료는 개인정보 보호를 위해 지번 일부를 가려서 제공합니다(예: 4**). 그래서 이 사이트는 개별 필지가 아니라 법정동(읍면동·리) 단위 통계로 보여줍니다.']
      pairs << ['평당가는 어떻게 계산했나요?', "지분 거래, 해제된 거래, 도로·하천·묘지 등 시세와 무관한 지목은 제외하고 거래금액 ÷ #{info['basis']}(평)을 구한 뒤 중앙값을 사용했습니다. 거래 건수가 적은 지역은 실제 시세와 차이가 클 수 있습니다."]
      faq(pairs)
    end
  end

  # ── 시도 허브 ───────────────────────────────────────
  class DoHubPage < LBasePage
    def initialize(site, k, do_short, sgs, latest, periods)
      info = LandGenerator::KINDS[k]
      setup(site, "#{k}/#{do_short}", 'hub')
      data['level'] = 'do'
      data['k'] = k
      data['info'] = info
      data['place'] = do_short
      data['doShort'] = do_short
      data['latest'] = latest
      n = sgs.sum { |s| s['n'] }
      data['n'] = f(n)
      data['sgRows'] = sgs.sort_by { |s| [-s['n'], s['sg']] }.map do |s|
        wc = s['w'][0][0] >= 3 && s['w'][1][0] >= 3 ? LText.chg(s['w'][0][1], s['w'][1][1]) : nil
        { 'name' => s['sg'], 'url' => LandGenerator.url(k, s['do'], s['sg']), 'n' => f(s['n']), 'n12' => f(s['n12']), 'med' => LText.py(s['med']), 'mp' => LText.man(s['mp']), 'chg' => LText.pct(wc), 'up' => wc && wc >= 0 }
      end
      best = sgs.select { |s| s['n'] >= 10 }.max_by { |s| s['med'] }
      busy = sgs.max_by { |s| s['n'] }
      s = +"#{do_short}에서 최근 36개월 동안 #{info['noun']} 매매 #{f(n)}건이 신고됐습니다(#{sgs.size}개 시군구). "
      s << "평당 가격(중앙값)이 가장 높은 시군구는 #{best['sg']}(#{LText.py(best['med'])}), " if best
      s << "거래가 가장 많은 곳은 #{busy['sg']}(#{f(busy['n'])}건)입니다. " if busy
      data['summary'] = s
      data['rankUrl'] = "/rank/#{k}/#{do_short}/"
      seo("#{do_short} #{info['title']} - 시군구별 #{info['name']} 실거래가·평당가", "#{do_short} #{info['long']}. 시군구별 평당 가격 중앙값과 거래 건수, 최근 변동.")
      faq([["#{do_short}에서 #{info['title']}이 가장 비싼 곳은 어디인가요?", best ? "거래 10건 이상인 시군구 중 평당 중앙값이 가장 높은 곳은 #{best['sg']}(#{LText.py(best['med'])})입니다. 같은 시군구 안에서도 동·리에 따라 차이가 크니 시군구 페이지의 동별 표를 확인하세요." : '비교할 수 있는 시군구가 부족합니다.']])
    end
  end

  # ── 종류 첫 화면 ────────────────────────────────────
  class KindIndexPage < LBasePage
    def initialize(site, k, sgs, latest, periods)
      info = LandGenerator::KINDS[k]
      setup(site, k, 'kindindex')
      data['k'] = k
      data['info'] = info
      data['latest'] = latest
      n = sgs.sum { |s| s['n'] }
      data['n'] = f(n)
      do_names = sgs.map { |s| s['do'] }.uniq.sort
      data['doRows'] = do_names.map do |d|
        l = sgs.select { |s| s['do'] == d }
        { 'name' => d, 'n' => f(l.sum { |s| s['n'] }), 'sg' => l.size }
      end
      data['top'] = sgs.select { |s| s['n'] >= LandGenerator::RANK_MIN_SG }.sort_by { |s| -s['med'] }.first(12).map { |s| { 'name' => "#{s['do']} #{s['sg']}", 'url' => LandGenerator.url(k, s['do'], s['sg']), 'med' => LText.py(s['med']), 'n' => f(s['n']) } }
      data['busy'] = sgs.sort_by { |s| -s['n'] }.first(12).map { |s| { 'name' => "#{s['do']} #{s['sg']}", 'url' => LandGenerator.url(k, s['do'], s['sg']), 'med' => LText.py(s['med']), 'n' => f(s['n']) } }
      data['summary'] = "전국 #{sgs.size}개 시군구의 #{info['long']} 최근 36개월 #{f(n)}건을 지역별로 정리했습니다. 시도와 시군구를 선택해 동·리 단위 평당가와 최근 거래를 확인하세요."
      seo("전국 #{info['title']} #{latest[0, 4]} - #{info['name']} 실거래가·평당가", "전국 #{info['long']} #{f(n)}건을 시도·시군구·동리별로 정리. 평당 가격 중앙값과 최근 12개월 변동, #{info['tl']}별 시세.")
    end
  end

  # ── 시군구×지목 ─────────────────────────────────────
  class JimokPage < LBasePage
    def initialize(site, r, latest, periods)
      jm = r['jm']
      label = LandGenerator::JM_LABEL[jm] || jm
      setup(site, "land-type/#{r['do']}/#{r['sg']}/#{jm}", 'jimok')
      place = "#{r['do']} #{r['sg']}"
      data['place'] = place
      data['doShort'] = r['do']
      data['sigungu'] = r['sg']
      data['jm'] = jm
      data['label'] = label
      data['latest'] = latest
      data['n'] = f(r['n'])
      data['n12'] = f(r['n12'])
      data['med'] = LText.py(r['med'])
      data['medSqm'] = LText.fmt((r['med'] / 3.3058).round)
      data['mp'] = LText.man(r['mp'])
      data['wRows'] = LandGenerator.win_rows(r, periods)
      data['zones'] = r['z'].map { |z, n| { 'z' => z, 'n' => f(n) } }
      data['tRecent'] = LandGenerator.trade_rows(r, 'land')
      data['dl'] = (r['dl'] || []).map { |d, n, med| { 'name' => d, 'url' => LandGenerator.url('land', r['do'], r['sg'], d), 'n' => f(n), 'med' => LText.py(med) } }
      data['hubUrl'] = LandGenerator.url('land', r['do'], r['sg'])
      c = r['w'][0][0] >= 3 && r['w'][1][0] >= 3 ? LText.chg(r['w'][0][1], r['w'][1][1]) : nil
      s = +"#{place}의 #{label} 매매는 최근 36개월 #{f(r['n'])}건(최근 12개월 #{f(r['n12'])}건)이 신고됐습니다. 최근 12개월 평당 가격 중앙값은 #{LText.py(r['med'])}(㎡당 약 #{data['medSqm']}만원), 거래금액 중앙값은 #{LText.man(r['mp'])}입니다. "
      s << "직전 12개월 대비 평당 중앙값은 #{LText.pct(c)}입니다. " if c
      s << "주요 용도지역은 #{r['z'].first(2).map { |z, _| z }.join('·')}입니다." unless r['z'].empty?
      data['summary'] = s
      seo("#{place} #{label} 시세 - 평당가·실거래가 #{latest[0, 4]}", "#{place} #{label} 매매 실거래가: 최근 12개월 평당 #{LText.py(r['med'])}, 거래 #{f(r['n12'])}건. 동·리별 평당가와 최근 거래 내역.")
      faq([["#{place} #{label} 평당 시세는 얼마인가요?", "최근 12개월 신고된 거래의 평당 가격 중앙값은 #{LText.py(r['med'])}입니다. 지분 거래와 해제 거래는 제외했고, 필지의 위치·진입도로·용도지역에 따라 개별 가격은 크게 다릅니다."],
           ['표의 지번이 가려진 이유는 무엇인가요?', '실거래가 공개 자료가 개인정보 보호를 위해 지번 일부를 가려서 제공하기 때문입니다. 정확한 위치는 공식 실거래가 공개시스템과 토지이음에서 확인하세요.']])
    end
  end

  # ── 랭킹 ────────────────────────────────────────────
  class RankPage < LBasePage
    def initialize(site, k, do_short, sgs, dongs, tops, latest)
      info = LandGenerator::KINDS[k]
      setup(site, do_short ? "rank/#{k}/#{do_short}" : "rank/#{k}", 'rank')
      scope = do_short || '전국'
      data['k'] = k
      data['info'] = info
      data['scope'] = scope
      data['doShort'] = do_short
      data['latest'] = latest
      data['sgRows'] = sgs.each_with_index.map { |s, i| { 'rank' => i + 1, 'name' => do_short ? s['sg'] : "#{s['do']} #{s['sg']}", 'url' => LandGenerator.url(k, s['do'], s['sg']), 'n' => f(s['n']), 'med' => LText.py(s['med']), 'mp' => LText.man(s['mp']) } }
      data['dongRows'] = dongs.each_with_index.map { |d, i| { 'rank' => i + 1, 'name' => "#{d['sg']} #{d['dong']}", 'url' => LandGenerator.url(k, d['do'], d['sg'], d['dong']), 'n' => f(d['n']), 'med' => LText.py(d['med']) } }
      data['tops'] = tops.map do |ymd, ty, a, amt, py, dg, jb, sg, d|
        { 'd' => LText.date(ymd), 'ty' => ty, 'a' => LText.area(a), 'amt' => LText.man(amt), 'py' => LText.py(py), 'loc' => [d, sg, dg].compact.join(' '), 'jb' => jb }
      end
      data['summary'] = "#{scope}의 #{info['long']} 최근 36개월 신고 자료로 만든 순위입니다. 평당 가격은 지분·해제 거래와 시세와 무관한 지목을 제외한 중앙값이며, 거래 건수가 적은 지역은 순위에서 제외했습니다."
      seo("#{scope} #{info['title']} 순위 - 평당가 높은 지역과 최고가 거래 #{latest[0, 4]}", "#{scope} #{info['name']} 매매 평당가 순위와 최근 12개월 고가 거래 TOP. 시군구·동리별 평당 가격 중앙값 비교.")
    end
  end

  class RankIndexPage < LBasePage
    def initialize(site, latest, present)
      setup(site, 'rank', 'rank')
      data['index'] = true
      data['latest'] = latest
      data['kinds'] = present.map { |k| LandGenerator::KINDS[k].merge('k' => k) }
      seo("땅값·상가 시세 순위 - 평당가 높은 지역과 최고가 거래", '토지·상가·공장창고·단독주택 매매 실거래가로 만든 평당가 순위와 최고가 거래 TOP. 전국·시도별로 확인하세요.')
    end
  end

  # 사이트맵: 5만 건 한도 때문에 40,000건씩 분할 + 인덱스
  class LandSitemapGenerator < Generator
    safe true
    priority :lowest
    CHUNK = 40_000

    def generate(site)
      urls = site.pages.reject { |p| p.url.to_s.end_with?('.json', '.xml', '.txt', '.js', '.css') || p.url.to_s == '/404.html' || p.data['sitemap'] == false }.map { |p| p.url }.uniq
      base = site.config['url'].to_s
      chunks = urls.each_slice(CHUNK).to_a
      chunks.each_with_index do |c, idx|
        body = +"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
        c.each { |u| body << "  <url><loc>#{base}#{u}</loc></url>\n" }
        body << "</urlset>\n"
        site.pages << raw_page(site, "sitemap-#{idx + 1}.xml", body)
      end
      index = +"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
      chunks.each_index { |idx| index << "  <sitemap><loc>#{base}/sitemap-#{idx + 1}.xml</loc></sitemap>\n" }
      index << "</sitemapindex>\n"
      site.pages << raw_page(site, 'sitemap.xml', index)
      Jekyll.logger.info 'LandSitemap:', "#{urls.size}개 URL → #{chunks.size}개 사이트맵"
    end

    private

    def raw_page(site, name, content)
      pg = PageWithoutAFile.new(site, site.source, '', name)
      pg.content = content
      pg.data['layout'] = nil
      pg.data['sitemap'] = false
      pg
    end
  end
end
