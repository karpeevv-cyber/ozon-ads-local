"use client";

import { FormEvent, useState } from "react";

import { applyBid } from "@/shared/api/client";

type BidApplyCardProps = {
  company: string;
};

export function BidApplyCard({ company }: BidApplyCardProps) {
  const [campaignId, setCampaignId] = useState("");
  const [sku, setSku] = useState("");
  const [bidRub, setBidRub] = useState("");
  const [reason, setReason] = useState("Manual");
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setStatus("");
    try {
      const result = await applyBid({
        company,
        campaign_id: campaignId,
        sku,
        bid_rub: Number(bidRub),
        reason,
        comment,
      });
      setStatus(
        `Applied ${result.reason}: ${result.old_bid_micro ?? "n/a"} -> ${result.new_bid_micro}`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to apply bid");
    } finally {
      setLoading(false);
    }
  }

  return (
    <article className="panel-card panel-card-wide">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Bids</p>
          <h3>Apply bid</h3>
        </div>
      </div>
      <form className="bid-form" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Campaign ID"
          value={campaignId}
          onChange={(e) => setCampaignId(e.target.value)}
          required
        />
        <input type="text" placeholder="SKU" value={sku} onChange={(e) => setSku(e.target.value)} required />
        <input
          type="number"
          step="0.01"
          placeholder="Bid RUB"
          value={bidRub}
          onChange={(e) => setBidRub(e.target.value)}
          required
        />
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          <option value="Manual">Manual</option>
          <option value="Test">Test</option>
          <option value="Optimization">Optimization</option>
        </select>
        <input
          type="text"
          placeholder="Comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Applying..." : "Apply bid"}
        </button>
      </form>
      {status ? <p className="muted-copy">{status}</p> : null}
    </article>
  );
}
