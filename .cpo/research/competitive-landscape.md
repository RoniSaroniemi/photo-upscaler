# Competitive Landscape — Image Upscaling (March 2026)

## Key Finding

**Zero competitors show a cost breakdown.** Every service uses credits, tokens, or subscription bundles to obscure the actual per-image cost. The "show the math" approach is genuinely novel.

## Pricing Summary

| Service | Free Tier | Cheapest Paid | Est. Per-Image Cost | Model |
|---------|-----------|---------------|---------------------|-------|
| Let's Enhance | 10 images (one-time) | $9/mo (100 img) | ~$0.09 | Subscription+credits |
| Upscale.media | 3/month | ~€10/mo | ~€0.10 | Subscription+credits |
| Bigjpg | 20/month | $6/2mo (500/mo) | ~$0.006 | Time-limited sub |
| waifu2x | Unlimited (web) | Free | $0 | Open source |
| Topaz Labs | None | $199/year | ~$0.55 (1/day) | Subscription |
| Adobe Enhance | Limited credits | $20/month | Bundled | CC Subscription |
| Magnific AI | None | $39/mo (200 img) | ~$0.20 | Subscription+tokens |
| Upscayl | Unlimited (local) | Free | $0 (your GPU) | Open source |
| **Honest Image Tools** | **TBD** | **Pay-per-use** | **Target <$0.05** | **Pay-what-it-costs** |

## Top User Complaints (across all services)

1. **Subscription fatigue** — Topaz backlash is the clearest signal. Many users upscale photos rarely, not daily.
2. **Credit/token systems that obscure costs** — Expiring credits, confusing exchange rates.
3. **Paying for features you don't need** — Adobe bundles into $240+/year suite.
4. **Bait-and-switch pricing** — Topaz eliminated perpetual licenses; widespread anger.
5. **No-refund on unused credits** — Magnific and others keep money on expiry.

## The Market Gap

The market splits into:
- **Expensive subscriptions** (Topaz $199-699/yr, Adobe $240/yr, Magnific $39/mo) — professionals pay grudgingly
- **Credit-based web services** (Let's Enhance, Upscale.media) — obscure real costs
- **Free/open-source local** (Upscayl, waifu2x) — requires GPU + technical knowledge

**Nobody occupies the middle: a simple web service with per-image pricing in real money, showing actual cost breakdown.**

At <$0.05/image, Honest Image Tools would be:
- 10-20x cheaper than Let's Enhance or Upscale.media per image
- Infinitely more accessible than Topaz/Adobe (no $200+/yr commitment)
- More convenient than Upscayl (no GPU required, no install)
- More honest than everyone (only service showing cost breakdown)

## Closest Competitors

- **Upscayl** — free, open source, uses Real-ESRGAN, runs locally. Philosophical alignment but requires GPU + technical setup.
- **Bigjpg** — cheapest paid option at ~$0.006/image but anime-focused, no transparency.
- **Replicate API** — ~$0.03/image developer API using Real-ESRGAN, but not a consumer product.

## Technology Landscape

Most competitors use proprietary models. Open-source alternatives (Real-ESRGAN, waifu2x) power several services under the hood. Real-ESRGAN is the current quality leader for photo upscaling. Topaz uses proprietary models considered gold standard by professionals.
