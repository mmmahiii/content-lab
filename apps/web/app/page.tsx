import { OperatorApp } from './prototype/operator-app';
import { OperatorProvider } from './prototype/provider';

export default function HomePage() {
  return (
    <OperatorProvider>
      <OperatorApp />
    </OperatorProvider>
  );
}
