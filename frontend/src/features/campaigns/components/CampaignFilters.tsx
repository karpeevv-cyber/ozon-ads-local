"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import { CompanyConfig } from "@/shared/api/types";

type CampaignFiltersProps = {
  companies: CompanyConfig[];
  selectedCompany: string;
  dateFrom: string;
  dateTo: string;
};

export function CampaignFilters({
  companies,
  selectedCompany,
  dateFrom,
  dateTo,
}: CampaignFiltersProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function updateParam(name: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set(name, value);
    startTransition(() => {
      router.push(`/?${params.toString()}`);
    });
  }

  return (
    <section className="filters-card">
      <div className="filters-grid">
        <label>
          <span>Company</span>
          <select
            value={selectedCompany}
            onChange={(event) => updateParam("company", event.target.value)}
            disabled={isPending}
          >
            {companies.map((company) => (
              <option key={company.name} value={company.name}>
                {company.display_name || company.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Date from</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => updateParam("date_from", event.target.value)}
            disabled={isPending}
          />
        </label>
        <label>
          <span>Date to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(event) => updateParam("date_to", event.target.value)}
            disabled={isPending}
          />
        </label>
      </div>
    </section>
  );
}
