import { HStack } from "@astryxdesign/core/HStack";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";

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
    <IconButton
      className="app-icon-button"
      type="button"
      label={label}
      tooltip={label}
      icon={children}
      variant="ghost"
      onClick={onClick}
      isDisabled={disabled}
    />
  );
}
export function ErrorMessage({ error }: { error: string }) {
  return error ? (
    <Text as="p" className="error" role="alert">
      {error}
    </Text>
  ) : null;
}
export function Loading({ text }: { text: string }) {
  return (
    <HStack className="loading" role="status" gap={2} vAlign="center">
      <Spinner size="sm" aria-hidden="true" />
      <Text type="supporting">{text}</Text>
    </HStack>
  );
}
