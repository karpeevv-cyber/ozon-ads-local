import { BidChangeRecord, CampaignCommentRecord } from "@/shared/api/types";

type BidAuditPanelProps = {
  changes: BidChangeRecord[];
  comments: CampaignCommentRecord[];
};

function microToRub(value: number | null) {
  if (value == null) {
    return "n/a";
  }
  return (value / 1_000_000).toFixed(2);
}

export function BidAuditPanel({ changes, comments }: BidAuditPanelProps) {
  return (
    <>
      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Bids</p>
            <h3>Recent bid changes</h3>
          </div>
          <span className="status-badge">{changes.length} entries</span>
        </div>
        <div className="list-stack">
          {changes.length === 0 ? (
            <p className="muted-copy">No bid changes loaded yet.</p>
          ) : (
            changes.slice(0, 6).map((change) => (
              <div className="list-row" key={`${change.ts_iso}:${change.campaign_id}:${change.sku}`}>
                <div>
                  <strong>
                    {microToRub(change.old_bid_micro)}
                    {" -> "}
                    {microToRub(change.new_bid_micro)}
                  </strong>
                  <p>
                    Campaign {change.campaign_id} / SKU {change.sku} / {change.reason}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Comments</p>
            <h3>Campaign notes</h3>
          </div>
          <span className="status-badge">{comments.length} notes</span>
        </div>
        <div className="list-stack">
          {comments.length === 0 ? (
            <p className="muted-copy">No campaign comments loaded yet.</p>
          ) : (
            comments.slice(0, 6).map((comment) => (
              <div className="list-row" key={`${comment.ts}:${comment.campaign_id}`}>
                <div>
                  <strong>{comment.day || comment.ts}</strong>
                  <p>
                    Campaign {comment.campaign_id}: {comment.comment}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </article>
    </>
  );
}
