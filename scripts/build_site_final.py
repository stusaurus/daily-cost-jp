"""Final presentation layer for daily-cost-jp.

Keeps the API/filtering logic in build_site_entry.py and adds clearer unit labels
plus exact top-pick anchors for mobile navigation.
"""
import build_site_entry as app

core = app.core


def display_metric_label(item, metric):
    """Use human-readable units and never show an ambiguous '1個' for tissues."""
    if metric == "box":
        return "1箱"
    if metric == "pack":
        return "1パック"
    return core.METRIC_LABELS.get(metric, metric)


def render_product_card_final(item, rank, metric, anchor_id):
    name = core.html.escape(app.clean_display_name(item["name"]))
    shop = core.html.escape(item["shop"])
    url = core.html.escape(item["url"], quote=True)
    image = core.html.escape(item["image"], quote=True)
    metric_label = display_metric_label(item, metric)
    review = (
        f"★ {item['review_average']:.2f}（{item['review_count']:,}件）"
        if item["review_count"] > 0
        else "レビュー情報なし"
    )
    point = (
        f"ポイント {item['point_rate']}倍"
        if item["point_rate"] > 1
        else "通常ポイント"
    )
    image_html = (
        f'<img src="{image}" alt="" loading="lazy">'
        if image
        else '<div class="image-placeholder">画像なし</div>'
    )

    return f"""
    <article id="{core.html.escape(anchor_id)}" class="product-card product-card-anchor">
      <div class="rank-badge">{rank}</div>
      <div class="product-image">{image_html}</div>
      <div class="product-body">
        <h3>{name}</h3>
        <div class="unit-price">{core.yen(item["unit_price"])} <span>/ {metric_label}</span></div>
        <div class="meta-grid">
          <span>商品価格 <strong>¥{item["price"]:,}</strong></span>
          <span class="shipping-chip">送料込み</span>
          <span>{core.html.escape(review)}</span>
          <span>{core.html.escape(point)}</span>
        </div>
        <p class="shop">{shop}</p>
        <a class="buy-button" href="{url}" target="_blank" rel="nofollow sponsored noopener">楽天市場で確認する</a>
      </div>
    </article>
    """


def render_category_final(category, items, error=None):
    anchor = core.html.escape(category["id"])
    heading = f'{category["emoji"]} {core.html.escape(category["name"])}'
    if error:
        return f"""
        <section id="{anchor}" class="category-section">
          <div class="section-heading"><h2>{heading}</h2></div>
          <div class="notice">現在データを取得できませんでした。次回の自動更新で再試行します。</div>
        </section>
        """

    metric, ranked = core.choose_ranked_items(items)
    if not ranked:
        return f"""
        <section id="{anchor}" class="category-section">
          <div class="section-heading"><h2>{heading}</h2></div>
          <div class="notice">単価を安全に計算できる送料込み商品が不足しています。推測値は表示していません。</div>
        </section>
        """

    metric_label = display_metric_label(ranked[0], metric)
    cards = "\n".join(
        render_product_card_final(
            item,
            index,
            metric,
            f"{category['id']}-rank-{index}",
        )
        for index, item in enumerate(ranked, start=1)
    )
    return f"""
    <section id="{anchor}" class="category-section">
      <div class="section-heading">
        <h2>{heading}</h2>
        <p>送料込み商品のうち、同じ単位（{metric_label}）で比較できる商品を安い順に表示</p>
      </div>
      <div class="product-list">{cards}</div>
    </section>
    """


def render_top_picks_final(category_snapshots):
    cards = []
    for category, metric, ranked in category_snapshots:
        if not ranked or not metric:
            continue
        item = ranked[0]
        label = display_metric_label(item, metric)
        short_name = app.clean_display_name(item["name"])
        cards.append(f"""
        <a class="top-pick" href="#{core.html.escape(category['id'])}-rank-1">
          <span class="top-pick-category">{category['emoji']} {core.html.escape(category['name'])}</span>
          <strong>{core.yen(item['unit_price'])}</strong>
          <span class="top-pick-unit">/ {core.html.escape(label)}</span>
          <span class="top-pick-name">{core.html.escape(short_name)}</span>
          <small>1位の商品へ ↓</small>
        </a>
        """)
    if not cards:
        return ""
    return f"""
    <section class="top-picks" aria-label="今日のコスパ1位">
      <div class="top-picks-heading">
        <span>今日のコスパ1位</span>
        <small>送料込み商品から比較</small>
      </div>
      <div class="top-picks-grid">{''.join(cards)}</div>
    </section>
    """


# build_site_improved() resolves these globals/modules at runtime.
core.render_category = render_category_final
app.render_top_picks = render_top_picks_final

FINAL_CSS = r"""
    .product-card-anchor { scroll-margin-top: 78px; }
    .product-card-anchor:target {
      border-color: #d97b73;
      box-shadow: 0 0 0 3px rgba(179,38,30,.10), 0 5px 20px rgba(0,0,0,.06);
    }
    .top-pick-name {
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      color: #4b5563;
      font-size: 10px;
      line-height: 1.45;
      margin-top: 4px;
      min-height: 2.9em;
    }
    .top-pick:active { transform: scale(.985); }
"""
app.IMPROVED_HEAD = app.IMPROVED_HEAD.replace("  </style>", FINAL_CSS + "\n  </style>")


if __name__ == "__main__":
    core.build_site()
