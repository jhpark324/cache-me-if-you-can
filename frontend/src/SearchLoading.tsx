import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import "./SearchLoading.css";

export default function SearchLoading({ text }: { text: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = performance.now();
    const timer = window.setInterval(() => {
      setSeconds(Math.floor((performance.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="search-loading">
      <div className="search-loading-heading">
        <LoaderCircle className="search-loading-spinner" aria-hidden="true" />
        <span>{text}</span>
        <span className="search-loading-elapsed" aria-hidden="true">
          {seconds}초
        </span>
      </div>
      <div className="search-loading-lines" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}
