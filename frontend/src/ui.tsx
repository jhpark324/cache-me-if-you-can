import { IconButton, Tooltip } from "@radix-ui/themes";
import { LoaderCircle } from "lucide-react";

export function Tool({
  label,
  children,
  onClick,
  disabled = false,
}: {
  label: string;
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <Tooltip content={label}>
      <IconButton
        type="button"
        aria-label={label}
        variant="ghost"
        onClick={onClick}
        disabled={disabled}
      >
        {children}
      </IconButton>
    </Tooltip>
  );
}
export function ErrorMessage({ error }: { error: string }) {
  return error ? (
    <p className="error" role="alert">
      {error}
    </p>
  ) : null;
}
export function Loading({ text }: { text: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle />
      {text}
    </div>
  );
}
