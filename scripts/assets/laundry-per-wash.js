/* Purchase planning stays local; GA4 receives only completion flags, never household inputs. */
(function (root, makeModule) {
  'use strict';
  const api = makeModule();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') api.mount(document);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function positive(value, label, integer) {
    if (value === '' || value === null || value === undefined) {
      throw new Error(label + 'を入力してください。');
    }
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0 || number > 1000000000 ||
        (integer && !Number.isInteger(number))) {
      throw new Error(label + 'には正しい正の数を入力してください。');
    }
    return number;
  }
  function nonnegative(value, label) {
    if (value === '' || value === null || value === undefined) return 0;
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0 || number > 1000000000) {
      throw new Error(label + 'には0以上の数を入力してください。');
    }
    return number;
  }
  function offer(raw, label) {
    const price = positive(raw.price, label + 'の税込セット価格');
    if (raw.shipping === undefined || raw.shipping === null || raw.shipping === '') {
      throw new Error(label + 'の1セット送料を確認してください。送料無料なら0を入力してください。');
    }
    const shipping = nonnegative(raw.shipping, label + 'の送料');
    const content = positive(raw.content, label + 'の1個あたり内容量');
    const packs = positive(raw.packs, label + 'の入り数', true);
    const dose = positive(raw.dose, label + 'の1回使用量');
    const quantity = content * packs;
    if (!Number.isFinite(quantity) || quantity > 1000000000 || dose > quantity) {
      throw new Error(label + 'の使用量が内容量を超えています。');
    }
    const total = price + shipping;
    if (!Number.isFinite(total) || total > 1000000000) {
      throw new Error(label + 'の支払総額を確認してください。');
    }
    return {
      orderShipping: raw.orderShipping === undefined || raw.orderShipping === '' ? null : nonnegative(raw.orderShipping, label + 'の今回の注文全体の送料'),
      price: price,
      shipping: shipping,
      total: total,
      totalContent: quantity,
      dose: dose,
      washes: quantity / dose,
      perWash: total * dose / quantity
    };
  }
  // Multiple-set checkout needs the user-confirmed shipping for that entire order.
  function purchaseForPeriod(item, washCount) {
    const required = washCount * item.dose;
    const packsToBuy = Math.ceil(required / item.totalContent);
    const shipping = packsToBuy === 1 ? item.shipping : item.orderShipping;
    const payment = shipping === null || shipping === undefined ? null : packsToBuy * item.price + shipping;
    const left = Math.max(0, packsToBuy * item.totalContent - required);
    if (packsToBuy * item.price > 1000000000 || !Number.isSafeInteger(packsToBuy) || (payment !== null && !Number.isFinite(payment)) ||
        payment > 1000000000 || !Number.isFinite(left)) {
      throw new Error('購入見積の金額または数量が大きすぎます。期間・入力値を確認してください。');
    }
    return {sets: packsToBuy, payment: payment, unused: left};
  }
  function compare(rawA, rawB, monthly, months = 1) {
    const a = offer(rawA, '洗剤A');
    const b = offer(rawB, '洗剤B');
    const times = positive(monthly, '月の洗濯回数', true);
    const period = positive(months, '比較期間', true);
    if (times > 1000) throw new Error('月の洗濯回数が大きすぎます。');
    if (period > 12) throw new Error('比較期間は1〜12か月で入力してください。');
    const delta = a.perWash - b.perWash;
    const winner = Math.abs(delta) < 0.000001 ? 'same' : delta < 0 ? 'A' : 'B';
    const washesNeeded = times * period;
    const purchaseA = purchaseForPeriod(a, washesNeeded);
    const purchaseB = purchaseForPeriod(b, washesNeeded);
    const purchaseWinner = purchaseA.payment === null || purchaseB.payment === null ? null : purchaseA.payment === purchaseB.payment ? 'same' :
      purchaseA.payment < purchaseB.payment ? 'A' : 'B';
    return {
      a: a, b: b, monthly: times, months: period, washesNeeded: washesNeeded,
      winner: winner,
      purchaseA: purchaseA, purchaseB: purchaseB, purchaseWinner: purchaseWinner,
      purchaseDifference: purchaseWinner === null ? null : Math.abs(purchaseA.payment - purchaseB.payment),
      monthlyDifference: Math.abs(delta) * times,
      annualDifference: Math.abs(delta) * times * 12
    };
  }
  function mark(name, flags) {
    // Production injects the site's existing GA4 wrapper after this script loads.
    // No prices, doses, quantities or household usage inputs are transmitted.
    const gtag = typeof window !== 'undefined' && window.gtag;
    if (typeof gtag === 'function') gtag('event', name, {
      category_id: 'laundry', tool_id: 'laundry_per_wash', ...flags
    });
  }
  function mount(doc) {
    const form = doc.getElementById('wash-calc');
    if (!form) return;
    const byId = id => doc.getElementById(id);
    const result = byId('wash-result');
    const error = byId('wash-error');
    const money = n => n.toLocaleString('ja-JP', {maximumFractionDigits: 2,
                                                minimumFractionDigits: 2});
    const read = key => ({
      price: byId(key + '-price').value,
      shipping: byId(key + '-shipping').value,
      orderShipping: byId(key + '-order-shipping').value,
      content: byId(key + '-content').value,
      packs: byId(key + '-packs').value,
      dose: byId(key + '-dose').value
    });
    function calculate(event) {
      event.preventDefault();
      error.textContent = '';
      result.hidden = true;
      try {
        const r = compare(read('wash-a'), read('wash-b'),
          byId('wash-monthly').value, byId('wash-period').value);
        byId('wash-a-cost').textContent = money(r.a.perWash) + '円';
        byId('wash-b-cost').textContent = money(r.b.perWash) + '円';
        byId('wash-a-uses').textContent = r.a.washes.toFixed(1) + '回分';
        byId('wash-b-uses').textContent = r.b.washes.toFixed(1) + '回分';
        const verdict = r.winner === 'same' ? '入力条件では同額です。' :
          '入力条件では洗剤' + r.winner + 'が1回あたり安くなります。';
        byId('wash-verdict').textContent = verdict;
        byId('wash-month-diff').textContent = money(r.monthlyDifference) + '円';
        byId('wash-year-diff').textContent = money(r.annualDifference) + '円';
        byId('wash-purchase-count').textContent =
          r.months + 'か月・' + r.washesNeeded + '回分';
        for (const [key, purchase] of [['a', r.purchaseA], ['b', r.purchaseB]]) {
          byId('wash-' + key + '-payment').textContent = purchase.payment === null ? '送料未確認のため未算出' : money(purchase.payment) + '円';
          byId('wash-' + key + '-sets').textContent =
            purchase.sets + 'セット購入（' +
            (purchase.sets * Number(byId('wash-' + key + '-packs').value)) + '個）';
          byId('wash-' + key + '-unused').textContent =
            '使用後の余り 約' +
            purchase.unused.toLocaleString('ja-JP', {maximumFractionDigits: 2}) +
            byId('wash-' + key + '-unit').value;
        }
        byId('wash-purchase-verdict').textContent =
          r.purchaseWinner === null ? '複数セットを注文するときの送料合計を販売店で確認し、入力すると支払額を比較できます。' :
          r.purchaseWinner === 'same' ?
            'この期間に必要な分の購入見積は同額です。' :
            'この期間の購入見積では洗剤' + r.purchaseWinner +
            'が' + money(r.purchaseDifference) + '円少ない支払額です。';
        const purchaseReversed = r.purchaseWinner !== null && r.purchaseWinner !== 'same' &&
          r.winner !== 'same' && r.purchaseWinner !== r.winner;
        byId('wash-purchase-tradeoff').textContent =
          purchaseReversed ?
            '注意：1回あたりの安さと、この期間の購入支払額は逆転しています。' +
            '余った分を後で使うか、今の支払いを抑えるかで選び方が変わります。' : '';
        result.hidden = false;
        mark('laundry_purchase_plan_complete', {
          example_mode: byId('wash-example-note').hidden ? '0' : '1',
          purchase_winner_reversed: purchaseReversed ? '1' : '0'
        });
      } catch (e) {
        error.textContent = e.message;
      }
    }
    form.addEventListener('submit', calculate);
    for (const button of doc.querySelectorAll('[data-pick-target]')) {
      button.addEventListener('click', function () {
        const key = button.dataset.pickTarget;
        const price = Number(button.dataset.pickPrice);
        const total = Number(button.dataset.pickTotal);
        const unit = button.dataset.pickUnit;
        if (!['a', 'b'].includes(key) || !(price > 0) || !(total > 0) ||
            !['g', 'mL'].includes(unit)) return;
        // A fictional sample must not silently remain as the other product.
        if (!byId('wash-example-note').hidden) {
          const other = key === 'a' ? 'b' : 'a';
          for (const field of ['price', 'shipping', 'order-shipping', 'content', 'dose']) {
            byId('wash-' + other + '-' + field).value = '';
          }
          byId('wash-' + other + '-packs').value = '1';
        }
        // One verified sale bundle is one calculator item; never invent bag counts.
        byId('wash-' + key + '-price').value = String(price);
        byId('wash-' + key + '-shipping').value = '0';
        // A new offer invalidates any shipping previously entered for multiple sets.
        byId('wash-' + key + '-order-shipping').value = '';
        byId('wash-' + key + '-content').value = String(total);
        byId('wash-' + key + '-packs').value = '1';
        byId('wash-' + key + '-unit').value = unit;
        // Dosage cannot be inferred from the offer title or another product.
        byId('wash-' + key + '-dose').value = '';
        byId('wash-picked-note').textContent =
          '洗剤' + key.toUpperCase() + 'に「' +
          (button.dataset.pickName || '掲載候補') +
          '」の価格と1販売セットの総内容量を入力しました。' +
          '洗濯機の条件に合う1回使用量を製品ラベルで確認してください。';
        byId('wash-example-note').hidden = true;
        result.hidden = true;
        error.textContent = '';
        mark('laundry_verified_offer_prefill', {slot: key.toUpperCase()});
        byId('wash-' + key + '-dose').focus();
      });
    }
    const shop = doc.querySelector('.purchase-horizon a[href="/daily-cost-jp/categories/laundry/"]');
    if (shop) shop.addEventListener('click', () => mark('laundry_purchase_plan_to_products', {}));
    byId('wash-sample').addEventListener('click', function () {
      // Deliberately fictional inputs. Not product prices, not a sales claim.
      const sample = {
        'wash-a-price': 598, 'wash-a-shipping': 0, 'wash-a-content': 1000,
        'wash-a-packs': 1, 'wash-a-dose': 30,
        'wash-b-price': 1880, 'wash-b-shipping': 0, 'wash-b-content': 900,
        'wash-b-packs': 2, 'wash-b-dose': 15,
        'wash-monthly': 20, 'wash-period': 3, 'wash-a-order-shipping': 0, 'wash-b-order-shipping': 0
      };
      for (const [id, value] of Object.entries(sample)) byId(id).value = value;
      byId('wash-example-note').hidden = false;
      byId('wash-picked-note').textContent = '';
      form.requestSubmit();
    });
    form.addEventListener('reset', function () {
      result.hidden = true;
      error.textContent = '';
      byId('wash-example-note').hidden = true;
      byId('wash-picked-note').textContent = '';
    });
    for (const input of form.querySelectorAll('input, select')) {
      const invalidate = function () {
        result.hidden = true;
        error.textContent = '';
        const orderSizeChanged = input.id === 'wash-monthly' || input.id === 'wash-period';
        for (const key of ['a', 'b']) {
          const productTermsChanged = input.id.startsWith('wash-' + key + '-') &&
            ['price', 'shipping', 'content', 'packs', 'dose', 'unit'].includes(
              input.id.slice(('wash-' + key + '-').length));
          if (orderSizeChanged || productTermsChanged) {
            const confirmedShipping = byId('wash-' + key + '-order-shipping');
            if (confirmedShipping.value !== '') {
              confirmedShipping.value = '';
              error.textContent =
                '購入条件が変わったため、複数セット注文の送料合計を再確認してください。';
            }
          }
        }
        if (/^wash-[ab]-(price|shipping|content|packs|unit)$/.test(input.id) &&
            byId('wash-picked-note').textContent) {
          byId('wash-picked-note').textContent =
            '価格・容量・販売単位を手動で変更しました。現在の入力は掲載候補と異なる場合があります。';
        }
        // Sample values remain in other fields after any individual edit.
        // Keep their fictional provenance visible until the form is reset.
      };
      input.addEventListener('input', invalidate);
      input.addEventListener('change', invalidate);
    }
  }
  return {offer, purchaseForPeriod, compare, mount};
});
