const sponsors = [
  { file: "partner-03.svg", name: "Первый рекламный", href: "https://1reklama.com/", featured: true },
  { file: "partner-04.png", name: "Славда", href: "https://www.slavda.ru/", featured: true },
  { file: "partner-05.png", name: "Спорт-Марафон", href: "https://sport-marafon.ru/", featured: true },
  { file: "partner-08.png", name: "MyShark", href: "https://mysharkhv.ru/", inverted: true },
  { file: "do4a.svg", name: "MarketDo4a", href: "https://khabarovsk.marketdo4a.com/" },
  { file: "partner-10.png", name: "Тибет", href: "https://primalp.com/" },
  { file: "partner-11.png", name: "Hotto Ramen", href: "https://khv.hottoramen.ru/" },
  { file: "partner-13.png", name: "Birds&Blokes", href: "https://birdsandblokes.ru/" },
  { file: "partner-15.png", name: "ПроРок", inverted: true },
  { file: "partner-18.jpg", name: "Стенолаз", href: "https://stenolaz.ru/", featured: true },
  { file: "partner-20.png", name: "Ацтек", href: "https://aztec-climber.ru/", featured: true },
  { file: "scartaris.png", name: "Скартарис", href: "https://scartaris.ru/", featured: true },
  { file: "top-point.png", name: "Топ Поинт", href: "https://skalainfo.com/" },
  { file: "kant.svg", name: "Кант", href: "https://www.kant.ru/" },
];

export default function SponsorStrip() {
  return (
    <aside className="sponsor-strip" aria-label="Спонсоры фестиваля">
      {[true, false].map((featured) => (
        <div key={String(featured)} className={`sponsor-row${featured ? " sponsor-featured" : ""}`}>
          <div className="sponsor-track">
            {[false, true].map((duplicate) => (
              <div key={String(duplicate)} className="sponsor-group" aria-hidden={duplicate || undefined}>
                {sponsors.filter((sponsor) => Boolean(sponsor.featured) === featured).map(({ file, name, inverted }) => (
                  <span key={file}>
                    <img className={inverted ? "sponsor-inverted" : undefined} src={`/partners/${file}`} alt={duplicate ? "" : name} decoding="async" />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}
