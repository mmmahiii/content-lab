import { Composition } from 'remotion';
import { operationsBaseline, ratatouilleAssets } from './fixtures';
import { KineticReel } from './KineticReel';
import type { ReelTimeline } from './timeline';

const compositions: Array<{ id: string; timeline: ReelTimeline }> = [
  { id: 'OperationsBaseline', timeline: operationsBaseline },
  { id: 'RatatouilleAssets', timeline: ratatouilleAssets },
];

export const Root: React.FC = () => (
  <>
    {compositions.map(({ id, timeline }) => (
      <Composition
        key={id}
        id={id}
        component={KineticReel}
        fps={timeline.fps}
        durationInFrames={timeline.durationInFrames}
        width={timeline.width}
        height={timeline.height}
        defaultProps={timeline}
      />
    ))}
  </>
);
