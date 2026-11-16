import { useEffect, useState } from "react";
import { HStack } from "@astryxdesign/core/HStack";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

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
    <VStack className="search-loading" role="status" gap={2}>
      <HStack className="search-loading-heading" gap={3} vAlign="center">
        <Spinner size="lg" aria-hidden="true" />
        <Text type="body">{text}</Text>
        <Text
          type="supporting"
          className="search-loading-elapsed"
          hasTabularNumbers
          aria-hidden="true"
        >
          {seconds}초
        </Text>
      </HStack>
    </VStack>
  );
}
