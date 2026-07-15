export type PortalLinkStatus = "available" | "development";

export type PortalLink = {
  label: string;
  description: string;
} & (
  | {
      status: "available";
      href: `/${string}`;
    }
  | {
      status: "development";
      href?: `/${string}`;
    }
);

export type PortalSection = {
  title: string;
  rows: readonly PortalLink[];
};

export type PortalNotice = {
  title: string;
  content?: string;
  pinned?: boolean;
  date: string;
};

export const portalSections = [
  {
    title: "主檔管理",
    rows: [
      {
        label: "案場管理",
        description: "案場建立/更新/停用",
        href: "/master/site",
        status: "available",
      },
      {
        label: "電號管理",
        description: "電號建立/更新/停用",
        href: "/master/meter",
        status: "available",
      },
      {
        label: "房號管理",
        description: "房號建立/更新/停用",
        href: "/master/room",
        status: "available",
      },
      {
        label: "例外費用管理",
        description: "固定費用與例外款項",
        status: "development",
      },
      {
        label: "繳租確認管理",
        description: "電費試算、核准與發布",
        href: "/billing",
        status: "available",
      },
    ],
  },
  {
    title: "電費作業",
    rows: [
      {
        label: "房號度數上傳",
        description: "各期房號度數上傳",
        href: "/upload/reading",
        status: "available",
      },
      {
        label: "平均電價上傳",
        description: "各期台電帳單平均電價",
        href: "/upload/price",
        status: "available",
      },
    ],
  },
  {
    title: "資料查詢",
    rows: [
      {
        label: "通用資料檢視",
        description: "選任一張表→篩選→匯出Excel",
        href: "/data",
        status: "available",
      },
      {
        label: "稽核紀錄",
        description: "系統操作紀錄查詢",
        href: "/audit",
        status: "available",
      },
    ],
  },
] as const satisfies readonly PortalSection[];

export const portalNotices: readonly PortalNotice[] = [
  {
    title: "歡迎使用好室開發內部入口網站",
    pinned: true,
    date: "2025-12-16",
  },
  {
    title: "例外費用管理功能上線囉！",
    content: "請使用『例外費用管理』進行上傳",
    date: "2025-12-17",
  },
];
