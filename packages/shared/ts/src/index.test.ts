import { describe, expect, expectTypeOf, it } from 'vitest';

import type {
  ApiErrorResponse,
  HealthResponse,
  PackageDetailOut,
  PageCreate,
  PageOut,
  PolicyStateOut,
  ReelFamilyOut,
  ReelOut,
  ReelResponse,
  ReelTriggerCreate,
  RunCreateRequest,
  RunDetailOut,
} from './index';

describe('shared-ts contracts', () => {
  it('covers the phase-1 operator API surface', () => {
    const health: HealthResponse = { status: 'ok' };

    const pageCreate: PageCreate = {
      platform: 'instagram',
      display_name: 'Calm Educator',
      metadata: {
        persona: {
          label: 'Calm educator',
          audience: 'Busy founders',
          content_pillars: ['operations', 'positioning'],
        },
      },
    };

    const pageOut: PageOut = {
      id: 'page-1',
      org_id: 'org-1',
      platform: 'instagram',
      display_name: 'Calm Educator',
      external_page_id: null,
      handle: '@calm-educator',
      ownership: 'owned',
      metadata: {
        persona: {
          label: 'Calm educator',
          audience: 'Busy founders',
          brand_tone: ['clear'],
          content_pillars: ['operations'],
          differentiators: ['operator-led advice'],
          primary_call_to_action: null,
          extensions: {},
        },
        constraints: {
          banned_topics: [],
          blocked_phrases: ['guaranteed results'],
          required_disclosures: [],
          prohibited_claims: [],
          preferred_languages: ['en'],
          allow_direct_cta: true,
          max_script_words: 180,
          max_hashtags: 5,
        },
        niche: 'b2b-services',
      },
      created_at: '2026-04-09T10:00:00Z',
      updated_at: '2026-04-09T10:00:00Z',
    };

    const reelFamily: ReelFamilyOut = {
      id: 'family-1',
      org_id: 'org-1',
      page_id: 'page-1',
      name: 'Hooks',
      mode: 'explore',
      metadata: { niche: 'b2b-services' },
      variant_count: 1,
      variants: [
        {
          id: 'reel-1',
          origin: 'generated',
          status: 'ready',
          variant_label: 'A',
          external_reel_id: null,
          created_at: '2026-04-09T10:00:00Z',
          updated_at: '2026-04-09T10:00:00Z',
        },
      ],
      created_at: '2026-04-09T10:00:00Z',
      updated_at: '2026-04-09T10:00:00Z',
    };

    const reel: ReelOut = {
      id: 'reel-1',
      org_id: 'org-1',
      page_id: 'page-1',
      reel_family_id: reelFamily.id,
      origin: 'generated',
      status: 'posted',
      variant_label: 'A',
      external_reel_id: null,
      metadata: {
        review: {
          approved_at: '2026-04-09T10:05:00Z',
          approved_by: 'operator@example.com',
        },
        posting: {
          posted_at: '2026-04-09T10:10:00Z',
          posted_by: 'operator@example.com',
        },
      },
      approved_at: '2026-04-09T10:05:00Z',
      approved_by: 'operator@example.com',
      posted_at: '2026-04-09T10:10:00Z',
      posted_by: 'operator@example.com',
      created_at: '2026-04-09T10:00:00Z',
      updated_at: '2026-04-09T10:10:00Z',
    };

    const run: RunDetailOut = {
      id: 'run-1',
      org_id: 'org-1',
      workflow_key: 'process_reel',
      flow_trigger: 'reel_trigger',
      status: 'queued',
      idempotency_key: 'process-reel:org-1:page-1:reel-1',
      external_ref: 'outbox:event-1',
      input_params: {
        org_id: 'org-1',
        page_id: 'page-1',
        reel_id: 'reel-1',
      },
      output_payload: null,
      run_metadata: {
        submitted_via: 'api',
        flow_trigger: 'reel_trigger',
        orchestration: {
          backend: 'outbox',
        },
      },
      started_at: null,
      finished_at: null,
      created_at: '2026-04-09T10:00:00Z',
      updated_at: '2026-04-09T10:00:00Z',
      tasks: [
        {
          id: 'task-1',
          task_type: 'process_reel',
          status: 'queued',
          idempotency_key: 'process-reel:org-1:page-1:reel-1',
          payload: {
            org_id: 'org-1',
            page_id: 'page-1',
            reel_id: 'reel-1',
          },
          result: null,
          created_at: '2026-04-09T10:00:00Z',
          updated_at: '2026-04-09T10:00:00Z',
        },
      ],
      task_status_counts: {
        queued: 1,
      },
    };

    const policy: PolicyStateOut = {
      id: 'policy-1',
      org_id: 'org-1',
      scope_type: 'global',
      scope_id: null,
      state: {
        mode_ratios: {
          exploit: 0.3,
          explore: 0.4,
          mutation: 0.2,
          chaos: 0.1,
        },
        budget: {
          per_run_usd_limit: 10,
          daily_usd_limit: 40,
          monthly_usd_limit: 800,
        },
        thresholds: {
          similarity: {
            warn_at: 0.72,
            block_at: 0.88,
          },
          min_quality_score: 0.55,
        },
      },
      updated_at: '2026-04-09T10:00:00Z',
    };

    const packageDetail: PackageDetailOut = {
      run_id: run.id,
      org_id: 'org-1',
      status: 'succeeded',
      workflow_key: 'process_reel',
      reel_id: reel.id,
      package_root_uri: 's3://content-lab/reels/packages/reel-1',
      manifest_uri: 's3://content-lab/reels/packages/reel-1/package_manifest.json',
      manifest_metadata: {
        version: 1,
        artifact_count: 3,
      },
      manifest_download: {
        storage_uri: 's3://content-lab/reels/packages/reel-1/package_manifest.json',
        url: 'http://localhost:9000/content-lab/reels/packages/reel-1/package_manifest.json',
        expires_at: '2026-04-09T10:15:00Z',
      },
      provenance: {
        source: 'asset_registry',
      },
      provenance_uri: 's3://content-lab/reels/packages/reel-1/provenance.json',
      provenance_download: {
        storage_uri: 's3://content-lab/reels/packages/reel-1/provenance.json',
        url: 'http://localhost:9000/content-lab/reels/packages/reel-1/provenance.json',
        expires_at: '2026-04-09T10:15:00Z',
      },
      artifacts: [
        {
          name: 'final_video',
          storage_uri: 's3://content-lab/reels/packages/reel-1/final_video.mp4',
          kind: 'video',
          content_type: 'video/mp4',
          metadata: {
            filename: 'final_video.mp4',
          },
          download: {
            storage_uri: 's3://content-lab/reels/packages/reel-1/final_video.mp4',
            url: 'http://localhost:9000/content-lab/reels/packages/reel-1/final_video.mp4',
            expires_at: '2026-04-09T10:15:00Z',
          },
        },
      ],
      created_at: '2026-04-09T10:00:00Z',
      updated_at: '2026-04-09T10:15:00Z',
    };

    const trigger: ReelTriggerCreate = {
      metadata: {
        source: 'web',
      },
    };

    expect(health.status).toBe('ok');
    expect(pageCreate.metadata?.persona?.label).toBe('Calm educator');
    expect(pageOut.metadata.constraints.allow_direct_cta).toBe(true);
    expect(reelFamily.variants[0]?.status).toBe('ready');
    expect(reel.status).toBe('posted');
    expect(run.task_status_counts.queued).toBe(1);
    expect(policy.state.thresholds.similarity.block_at).toBeGreaterThan(
      policy.state.thresholds.similarity.warn_at,
    );
    expect(packageDetail.artifacts[0]?.name).toBe('final_video');
    expect(trigger.metadata?.source).toBe('web');
  });

  it('supports the operator detail contracts used by the demo routes', () => {
    const health: HealthResponse = { status: 'ok' };

    const page: PageOut = {
      id: '11111111-1111-4111-8111-111111111111',
      org_id: '22222222-2222-4222-8222-222222222222',
      platform: 'instagram',
      display_name: 'Northwind Ops',
      external_page_id: 'ig-northwind',
      handle: '@northwind.ops',
      ownership: 'owned',
      metadata: {
        persona: {
          label: 'Calm educator',
          audience: 'Busy founders',
          brand_tone: ['clear'],
          content_pillars: ['systems'],
          differentiators: ['operator-led'],
          primary_call_to_action: null,
          extensions: { voice: 'plainspoken' },
        },
        constraints: {
          banned_topics: [],
          blocked_phrases: ['guaranteed results'],
          required_disclosures: ['Results vary'],
          prohibited_claims: [],
          preferred_languages: ['en'],
          allow_direct_cta: true,
          max_script_words: 180,
          max_hashtags: 6,
        },
        niche: 'b2b-services',
      },
      created_at: '2026-04-09T10:00:00.000Z',
      updated_at: '2026-04-09T10:30:00.000Z',
    };

    const policy: PolicyStateOut = {
      id: '33333333-3333-4333-8333-333333333333',
      org_id: page.org_id,
      scope_type: 'page',
      scope_id: page.id,
      state: {
        mode_ratios: {
          exploit: 0.3,
          explore: 0.4,
          mutation: 0.2,
          chaos: 0.1,
        },
        budget: {
          per_run_usd_limit: 10,
          daily_usd_limit: 40,
          monthly_usd_limit: 800,
        },
        thresholds: {
          similarity: {
            warn_at: 0.72,
            block_at: 0.88,
          },
          min_quality_score: 0.55,
        },
      },
      updated_at: '2026-04-09T11:00:00.000Z',
    };

    const reel: ReelOut = {
      id: '44444444-4444-4444-8444-444444444444',
      org_id: page.org_id,
      page_id: page.id,
      reel_family_id: '55555555-5555-4555-8555-555555555555',
      origin: 'generated',
      status: 'ready',
      variant_label: 'A',
      external_reel_id: null,
      metadata: { editor_template: 'hook-fast-cut' },
      approved_at: '2026-04-09T12:00:00.000Z',
      approved_by: 'operator:reviewer',
      posted_at: null,
      posted_by: null,
      created_at: '2026-04-09T09:00:00.000Z',
      updated_at: '2026-04-09T12:00:00.000Z',
    };

    const run: RunDetailOut = {
      id: '66666666-6666-4666-8666-666666666666',
      org_id: page.org_id,
      workflow_key: 'process_reel',
      flow_trigger: 'reel_trigger',
      status: 'queued',
      idempotency_key: 'process-reel-4444',
      external_ref: 'prefect-flow-run-123',
      input_params: {
        org_id: page.org_id,
        page_id: page.id,
        reel_id: reel.id,
      },
      output_payload: null,
      run_metadata: {
        submitted_via: 'api',
      },
      started_at: '2026-04-09T12:05:00.000Z',
      finished_at: null,
      created_at: '2026-04-09T12:04:00.000Z',
      updated_at: '2026-04-09T12:05:00.000Z',
      tasks: [
        {
          id: '77777777-7777-4777-8777-777777777777',
          task_type: 'plan_reels',
          status: 'queued',
          idempotency_key: 'task-plan-001',
          payload: { family_count: 1 },
          result: null,
          created_at: '2026-04-09T12:04:30.000Z',
          updated_at: '2026-04-09T12:05:00.000Z',
        },
      ],
      task_status_counts: {
        queued: 1,
      },
    };

    const packageDetail: PackageDetailOut = {
      run_id: run.id,
      org_id: page.org_id,
      status: 'succeeded',
      workflow_key: 'process_reel',
      reel_id: reel.id,
      package_root_uri: 's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444',
      manifest_uri:
        's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444/package_manifest.json',
      manifest_metadata: { version: 1, artifact_count: 5 },
      manifest_download: {
        storage_uri:
          's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444/package_manifest.json',
        url: 'http://localhost:9000/content-lab/reels/packages/reel/package_manifest.json?sig=1',
        expires_at: '2026-04-09T13:00:00.000Z',
      },
      provenance: { source_run_id: run.id },
      provenance_uri:
        's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444/provenance.json',
      provenance_download: {
        storage_uri:
          's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444/provenance.json',
        url: 'http://localhost:9000/content-lab/reels/packages/reel/provenance.json?sig=1',
        expires_at: '2026-04-09T13:00:00.000Z',
      },
      artifacts: [
        {
          name: 'final_video',
          storage_uri:
            's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444/final_video.mp4',
          kind: 'video',
          content_type: 'video/mp4',
          metadata: {},
          download: {
            storage_uri:
              's3://content-lab/reels/packages/44444444-4444-4444-8444-444444444444/final_video.mp4',
            url: 'http://localhost:9000/content-lab/reels/packages/reel/final_video.mp4?sig=1',
            expires_at: '2026-04-09T13:00:00.000Z',
          },
        },
      ],
      created_at: '2026-04-09T12:04:00.000Z',
      updated_at: '2026-04-09T12:10:00.000Z',
    };

    expect(health.status).toBe('ok');
    expect(page.metadata.constraints.max_script_words).toBe(180);
    expect(policy.state.mode_ratios.explore).toBe(0.4);
    expect(reel.status).toBe('ready');
    expect(run.tasks[0]?.task_type).toBe('plan_reels');
    expect(packageDetail.artifacts[0]?.name).toBe('final_video');
  });

  it('supports operator console request and response aliases', () => {
    const run: RunCreateRequest = {
      workflow_key: 'daily_reel_factory',
      input_params: {},
      metadata: {},
    };
    const reel: ReelResponse = {
      id: '11111111-1111-4111-8111-111111111111',
      org_id: '11111111-1111-4111-8111-111111111111',
      page_id: '22222222-2222-4222-8222-222222222222',
      reel_family_id: '33333333-3333-4333-8333-333333333333',
      origin: 'generated',
      status: 'ready',
      variant_label: 'Ready cut',
      external_reel_id: null,
      metadata: {},
      approved_at: null,
      approved_by: null,
      posted_at: null,
      posted_by: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    const error: ApiErrorResponse = {
      detail: [
        {
          loc: ['body', 'input_params'],
          msg: 'Field required',
          type: 'missing',
        },
      ],
    };

    expect(run.workflow_key).toBe('daily_reel_factory');
    expect(reel.status).toBe('ready');
    expect(Array.isArray(error.detail)).toBe(true);
  });

  it('preserves narrowed operator contract unions', () => {
    expectTypeOf<RunDetailOut['workflow_key']>().toEqualTypeOf<
      'daily_reel_factory' | 'process_reel'
    >();
    expectTypeOf<ReelOut['status']>().toEqualTypeOf<
      | 'draft'
      | 'planning'
      | 'generating'
      | 'editing'
      | 'qa'
      | 'qa_failed'
      | 'ready'
      | 'posted'
      | 'archived'
      | 'active'
      | 'removed'
      | 'unavailable'
    >();
    expectTypeOf<PackageDetailOut['status']>().toEqualTypeOf<
      'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
    >();
  });
});
