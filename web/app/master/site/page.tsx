import { MasterPage, type MasterPageConfig } from "../_components/master-page";

const config: MasterPageConfig = {
  tableCode: "site",
  title: "案場管理",
  description: "維護案場代碼、名稱、地址與管理單位。",
  fields: [
    { key: "site_code", label: "案場代碼", required: true },
    { key: "name", label: "名稱" },
    { key: "address", label: "地址" },
    { key: "management_unit", label: "管理單位" },
  ],
};

export default function SiteMasterPage() {
  return <MasterPage config={config} />;
}
