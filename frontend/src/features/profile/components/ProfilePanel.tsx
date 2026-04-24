"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  createProfileCompany,
  getCurrentUser,
  getProfileCompanies,
  updateProfileCompany,
} from "@/shared/api/client";
import {
  CompanyProfile,
  CompanyProfilePayload,
  CurrentUser,
} from "@/shared/api/types";

type CompanyFormState = {
  id: number | null;
  name: string;
  display_name: string;
  perf_client_id: string;
  perf_client_secret: string;
  seller_client_id: string;
  seller_api_key: string;
  is_active: boolean;
};

const emptyForm: CompanyFormState = {
  id: null,
  name: "",
  display_name: "",
  perf_client_id: "",
  perf_client_secret: "",
  seller_client_id: "",
  seller_api_key: "",
  is_active: true,
};

function readToken(): string | null {
  try {
    return window.localStorage.getItem("ozon_ads_token");
  } catch {
    return null;
  }
}

function toForm(company: CompanyProfile): CompanyFormState {
  return {
    id: company.id,
    name: company.name,
    display_name: company.display_name,
    perf_client_id: company.perf_client_id,
    perf_client_secret: "",
    seller_client_id: company.seller_client_id,
    seller_api_key: "",
    is_active: company.is_active,
  };
}

function buildPayload(form: CompanyFormState, editing: boolean): CompanyProfilePayload {
  return {
    name: form.name.trim(),
    display_name: form.display_name.trim(),
    perf_client_id: form.perf_client_id.trim(),
    perf_client_secret: editing && !form.perf_client_secret.trim() ? undefined : form.perf_client_secret.trim(),
    seller_client_id: form.seller_client_id.trim(),
    seller_api_key: editing && !form.seller_api_key.trim() ? undefined : form.seller_api_key.trim(),
    is_active: form.is_active,
  };
}

export function ProfilePanel() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [companies, setCompanies] = useState<CompanyProfile[]>([]);
  const [form, setForm] = useState<CompanyFormState>(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function reload(nextToken: string) {
    const [nextUser, companyList] = await Promise.all([
      getCurrentUser(nextToken),
      getProfileCompanies(nextToken),
    ]);
    setUser(nextUser);
    setCompanies(companyList.companies);
  }

  useEffect(() => {
    const storedToken = readToken();
    if (!storedToken) {
      setLoading(false);
      return;
    }
    setToken(storedToken);
    reload(storedToken)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Profile load failed"))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setMessage("No auth token");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      if (form.id) {
        await updateProfileCompany(form.id, buildPayload(form, true), token);
        setMessage("Company updated");
      } else {
        await createProfileCompany(buildPayload(form, false), token);
        setMessage("Company added");
      }
      setForm(emptyForm);
      await reload(token);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Company save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <article className="panel-card panel-card-wide section-card skeleton-card">
        <div className="skeleton-line skeleton-line-lg" />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
      </article>
    );
  }

  return (
    <section className="profile-grid">
      <article className="panel-card panel-card-wide section-card profile-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Profile</p>
            <h3>Account</h3>
          </div>
          <span className="status-badge">{user?.is_admin ? "admin" : "member"}</span>
        </div>
        <div className="summary-grid">
          <div>
            <span>Name</span>
            <strong>{user?.full_name || "-"}</strong>
          </div>
          <div>
            <span>Email</span>
            <strong>{user?.email || "-"}</strong>
          </div>
          <div>
            <span>Companies</span>
            <strong>{companies.length}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>{user?.is_active ? "Active" : "Disabled"}</strong>
          </div>
        </div>
      </article>

      <article className="panel-card panel-card-wide section-card profile-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Companies</p>
            <h3>Ozon access keys</h3>
          </div>
          <button className="ghost-button" type="button" onClick={() => setForm(emptyForm)}>
            New
          </button>
        </div>

        <div className="profile-companies">
          {companies.length === 0 ? (
            <p className="muted-copy">No companies in profile yet.</p>
          ) : (
            companies.map((company) => (
              <button
                className={`company-row${form.id === company.id ? " company-row-active" : ""}`}
                key={company.id}
                type="button"
                onClick={() => setForm(toForm(company))}
              >
                <span>
                  <strong>{company.display_name}</strong>
                  <small>{company.name}</small>
                </span>
                <span>
                  <small>Seller {company.seller_client_id || "-"}</small>
                  <small>Perf {company.perf_client_id || "-"}</small>
                </span>
                <span className="status-badge">{company.is_active ? "active" : "off"}</span>
              </button>
            ))
          )}
        </div>

        <form className="profile-form" onSubmit={handleSubmit}>
          <label>
            <span>Company key</span>
            <input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="default"
              required
            />
          </label>
          <label>
            <span>Display name</span>
            <input
              value={form.display_name}
              onChange={(event) => setForm({ ...form, display_name: event.target.value })}
              placeholder="Aura Tea"
            />
          </label>
          <label>
            <span>Seller Client ID</span>
            <input
              value={form.seller_client_id}
              onChange={(event) => setForm({ ...form, seller_client_id: event.target.value })}
            />
          </label>
          <label>
            <span>Seller API Key</span>
            <input
              value={form.seller_api_key}
              onChange={(event) => setForm({ ...form, seller_api_key: event.target.value })}
              placeholder={form.id ? "leave blank to keep current" : ""}
            />
          </label>
          <label>
            <span>Performance Client ID</span>
            <input
              value={form.perf_client_id}
              onChange={(event) => setForm({ ...form, perf_client_id: event.target.value })}
            />
          </label>
          <label>
            <span>Performance Secret</span>
            <input
              value={form.perf_client_secret}
              onChange={(event) => setForm({ ...form, perf_client_secret: event.target.value })}
              placeholder={form.id ? "leave blank to keep current" : ""}
            />
          </label>
          <label className="profile-check">
            <span>Active</span>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
            />
          </label>
          <button className="stocks-primary-button" type="submit" disabled={saving || !user?.is_admin}>
            {form.id ? "Save company" : "Add company"}
          </button>
        </form>
        {message ? <p className="muted-copy">{message}</p> : null}
      </article>
    </section>
  );
}
