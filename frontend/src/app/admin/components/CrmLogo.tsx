import "../crm-brand.css";

export function CrmLogo({ variant = "full" }: { variant?: "full" | "header" | "compact" }) {
  const name = "ПаркРок — Управление соревнованиями";
  if (variant === "header") return <picture className="crm-logo crm-logo-header">
    <source media="(max-width: 760px)" srcSet="/brand/crm/compact-dark.svg" width={660} height={204}/>
    <img src="/brand/crm/full-dark.svg" alt={name} width={660} height={204}/>
  </picture>;
  return <img className={`crm-logo crm-logo-${variant}`} src={`/brand/crm/${variant === "compact" ? "compact" : "full"}-light.svg`} alt={name} width={660} height={204}/>;
}
