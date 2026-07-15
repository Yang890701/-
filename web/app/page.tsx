import Link from "next/link";
import { portalNotices, portalSections, type PortalLink } from "./portal-data";

function PortalRow({ row }: { row: PortalLink }) {
  const content = (
    <>
      <span className="portal-row-copy">
        <span className="portal-row-label">{row.label}</span>
        <span className="portal-row-description">{row.description}</span>
      </span>
      {row.status === "available" ? (
        <span className="portal-row-action">前往</span>
      ) : (
        <span className="portal-tag">開發中</span>
      )}
    </>
  );

  if (row.status === "available") {
    return (
      <Link className="portal-row portal-row-link" href={row.href}>
        {content}
      </Link>
    );
  }

  return (
    <div className="portal-row portal-row-disabled" aria-disabled="true">
      {content}
    </div>
  );
}

export default function PortalHomePage() {
  const notices = [
    ...portalNotices.filter((notice) => notice.pinned),
    ...portalNotices.filter((notice) => !notice.pinned),
  ];

  return (
    <main className="page portal-page">
      <div className="portal-heading">
        <p className="portal-kicker">內部入口</p>
        <h1>好室開發內部入口網站</h1>
        <p>主檔管理、電費作業與資料查詢</p>
      </div>

      <div className="portal-layout">
        <div className="portal-sections">
          {portalSections.map((section) => (
            <section className="card portal-card" key={section.title}>
              <h2 className="portal-card-title">{section.title}</h2>
              <div className="portal-list">
                {section.rows.map((row) => (
                  <PortalRow key={row.label} row={row} />
                ))}
              </div>
            </section>
          ))}
        </div>

        <aside className="portal-aside" aria-label="公告區">
          <section className="card portal-card">
            <h2 className="portal-card-title">公告區</h2>
            <div className="notice-list">
              {notices.map((notice) => (
                <article className="notice-item" key={`${notice.date}-${notice.title}`}>
                  <div className="notice-title-row">
                    <h3>{notice.title}</h3>
                    {notice.pinned ? <span className="notice-pin">置頂</span> : null}
                  </div>
                  {notice.content ? <p>{notice.content}</p> : null}
                  <time dateTime={notice.date}>{notice.date}</time>
                </article>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
