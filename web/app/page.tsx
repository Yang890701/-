"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiJson } from "../lib/api";

type PortalLinkItem = {
  title: string;
  url: string;
  description: string | null;
  is_new: boolean;
};

type PortalCategory = {
  category_code: string;
  category_name: string;
  links: PortalLinkItem[];
};

type PortalGroup = {
  group_code: string;
  group_name: string;
  categories: PortalCategory[];
};

type PortalNoticeItem = {
  title: string;
  content: string | null;
  pinned: boolean;
};

type PortalData = {
  groups: PortalGroup[];
  notices: PortalNoticeItem[];
};

function PortalRow({ link }: { link: PortalLinkItem }) {
  return (
    <Link className="portal-row portal-row-link" href={link.url}>
      <span className="portal-row-copy">
        <span className="portal-row-label">
          {link.title}
          {link.is_new ? <span className="portal-tag">新</span> : null}
        </span>
        {link.description ? (
          <span className="portal-row-description">{link.description}</span>
        ) : null}
      </span>
      <span className="portal-row-action">前往</span>
    </Link>
  );
}

export default function PortalHomePage() {
  const [data, setData] = useState<PortalData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    apiJson<PortalData>("/api/portal")
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "入口內容載入失敗");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page portal-page">
      <div className="portal-heading">
        <p className="portal-kicker">內部入口</p>
        <h1>好室開發內部入口網站</h1>
        <p>主檔管理、電費作業與資料查詢</p>
      </div>

      {loading ? <div className="loading">載入中</div> : null}
      {error ? <div className="error">{error}</div> : null}

      {data ? (
        <div className="portal-layout">
          <div className="portal-sections">
            {data.groups.map((group) => (
              <section className="card portal-card" key={group.group_code}>
                <h2 className="portal-card-title">{group.group_name}</h2>
                {group.categories.map((category) => (
                  <div className="portal-category" key={category.category_code}>
                    <h3 className="portal-category-title">{category.category_name}</h3>
                    <div className="portal-list">
                      {category.links.map((link) => (
                        <PortalRow key={link.url} link={link} />
                      ))}
                    </div>
                  </div>
                ))}
              </section>
            ))}
          </div>

          <aside className="portal-aside" aria-label="公告區">
            <section className="card portal-card">
              <h2 className="portal-card-title">公告區</h2>
              <div className="notice-list">
                {data.notices.map((notice, index) => (
                  <article className="notice-item" key={`${index}-${notice.title}`}>
                    <div className="notice-title-row">
                      <h3>{notice.title}</h3>
                      {notice.pinned ? <span className="notice-pin">置頂</span> : null}
                    </div>
                    {notice.content ? <p>{notice.content}</p> : null}
                  </article>
                ))}
              </div>
            </section>
          </aside>
        </div>
      ) : null}
    </main>
  );
}
