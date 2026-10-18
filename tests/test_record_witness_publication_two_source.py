"""Stage 263Y synthetic dual-source signed progression regressions."""
import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from tools import audit_record_witness_publication_live_source as live
from tools import audit_record_witness_publication_two_source as dual
from tools.audit_record_witness_fence_reconciliation import _sign


class DualAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key_temp=tempfile.TemporaryDirectory()
        cls.keys=[]
        folder=Path(cls.key_temp.name)
        for i in range(4):
            secret=folder/('secret-'+str(i)+'.pem')
            public=folder/('public-'+str(i)+'.pem')
            subprocess.run(['openssl','genpkey','-algorithm','ed25519',
                            '-out',str(secret)],check=True,capture_output=True)
            subprocess.run(['openssl','pkey','-in',str(secret),'-pubout',
                            '-out',str(public)],check=True,capture_output=True)
            secret.chmod(0o600)
            public.chmod(0o600)
            cls.keys.append((secret,public,
                    hashlib.sha256(public.read_bytes()).hexdigest()))

    @classmethod
    def tearDownClass(cls):
        cls.key_temp.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.counter=0
        self.scope='private-wild-arms-publication-mirrors'
        self.source_a=dict(source_url='https://source-a.example.org/heads/current',
                           authority_id='independent-authority-a',
                           authority_public=self.keys[0][1],
                           authority_pin=self.keys[0][2])
        self.source_b=dict(source_url='https://source-b.example.net/heads/current',
                           authority_id='independent-authority-b',
                           authority_public=self.keys[1][1],
                           authority_pin=self.keys[1][2])
        self.notaries=dict(notary_a_public=self.keys[2][1],
                           notary_a_pin=self.keys[2][2],
                           notary_b_public=self.keys[3][1],
                           notary_b_pin=self.keys[3][2])
        self.old=dict(count=1,head='1'*64,history='2'*64,witness='3'*64,
                      bundle='4'*64,challenge_a='a'*32,challenge_b='b'*32,
                      sequence_a=7,sequence_b=11)
        self.current=dict(count=2,head='5'*64,history='6'*64,
                          witness='7'*64,bundle='8'*64)
        self.challenge=('c'*32,'d'*32)
        self.old_raw_a=self.sign(self.source_a,0,self.old,
                                 challenge=self.old['challenge_a'],sequence=7)
        self.old_raw_b=self.sign(self.source_b,1,self.old,
                                 challenge=self.old['challenge_b'],sequence=11)
        self.pin=self.compute_pin()

    def compute_pin(self):
        return dual.checkpoint_digest(self.old_raw_a,self.old_raw_b,
               scope=self.scope,source_a_pin=self.source_a['authority_pin'],
               source_b_pin=self.source_b['authority_pin'])

    def sign(self,source,key_i,state,*,challenge,sequence,**changed):
        body={
            'schema':live.SCHEMA,
            'source_url':source['source_url'],
            'authority_id':source['authority_id'],
            'checkpoint_scope':self.scope,
            'challenge_nonce':challenge,'authority_sequence':sequence,
            'event_count':state['count'],
            'head_sha256':state['head'],
            'history_sha256':state['history'],
            'latest_witness_sha256':state['witness'],
            'notary_bundle_sha256':state['bundle'],
            'witness_fence_retirement_authorized':False,
        }
        body.update(changed)
        self.counter+=1
        output=Path(self.temp.name)/('reply-'+str(self.counter)+'.json')
        _sign(body,live.SCHEMA,live.DOMAIN,self.keys[key_i][0],output)
        return output.read_bytes()

    def fetch(self,url,scope,nonce):
        if url==self.source_a['source_url']:
            return self.sign(self.source_a,0,self.current,
                             challenge=nonce,sequence=8)
        if url==self.source_b['source_url']:
            return self.sign(self.source_b,1,self.current,
                             challenge=nonce,sequence=12)
        raise AssertionError('unexpected network destination')

    def check(self,**changes):
        args=dict(old_signed_a=self.old_raw_a,
                  old_signed_b=self.old_raw_b,
                  old_checkpoint_pin=self.pin,
                  old=self.old,current=self.current,
                  source_a=self.source_a,source_b=self.source_b,
                  notaries=self.notaries,scope=self.scope,
                  fetcher=self.fetch,challenges=self.challenge)
        args.update(changes)
        return dual.verify(**args)

    def test_two_sources_strictly_advance_from_externally_pinned_pair(self):
        report=self.check()
        self.assertTrue(report['each_authority_sequence_strictly_advanced'])
        self.assertTrue(report['new_event_count_strictly_advanced'])
        self.assertNotEqual(report['previous_checkpoint_sha256'],
                            report['proposed_new_checkpoint_sha256'])
        self.assertFalse(report['global_latest_head_proved'])
        self.assertFalse(report['witness_fence_retirement_authorized'])

    def test_list_of_valid_distinct_challenges_accepted(self):
        self.assertTrue(self.check(challenges=list(self.challenge))
                        ['two_new_challenge_bound_ed25519_claims_verified'])

    def test_old_pair_wrong_external_checkpoint_refused(self):
        with self.assertRaises(dual.DualSourceConflict):
            self.check(old_checkpoint_pin='f'*64)

    def test_old_pair_changed_first_envelope_refused(self):
        with self.assertRaises(dual.DualSourceConflict):
            self.check(old_signed_a=self.old_raw_a.replace(b'schema',b'schemx'))

    def test_old_pair_swapped_envelopes_refused(self):
        with self.assertRaises(dual.DualSourceConflict):
            self.check(old_signed_a=self.old_raw_b,old_signed_b=self.old_raw_a)

    def test_old_signed_sequence_does_not_match_independent_floor(self):
        old=self.old.copy()
        old['sequence_a']=8
        with self.assertRaises(live.LiveSourceConflict):
            self.check(old=old)

    def test_old_signed_tuple_tampered_even_with_recomputed_checkpoint(self):
        self.old_raw_b=self.sign(self.source_b,1,self.old,
             challenge=self.old['challenge_b'],sequence=11,
             history_sha256='e'*64)
        self.pin=self.compute_pin()
        with self.assertRaises(live.LiveSourceConflict):
            self.check()

    def test_new_first_authority_rolls_back_sequence(self):
        def fetch(url,scope,nonce):
            if url==self.source_a['source_url']:
                return self.sign(self.source_a,0,self.current,
                                 challenge=nonce,sequence=7)
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceConflict):
            self.check(fetcher=fetch)

    def test_new_second_authority_rolls_back_sequence(self):
        def fetch(url,scope,nonce):
            if url==self.source_b['source_url']:
                return self.sign(self.source_b,1,self.current,
                                 challenge=nonce,sequence=11)
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceConflict):
            self.check(fetcher=fetch)

    def test_same_count_is_not_strict_advancement(self):
        current=self.current.copy()
        current['count']=1
        with self.assertRaises(dual.DualSourceConflict):
            self.check(current=current)

    def test_advanced_count_with_unchanged_commitment_refused(self):
        for key in ('head','history','witness','bundle'):
            with self.subTest(key=key):
                current=self.current.copy()
                current[key]=self.old[key]
                with self.assertRaises(dual.DualSourceConflict):
                    self.check(current=current)

    def test_boolean_event_count_rejected(self):
        current=self.current.copy()
        current['count']=True
        with self.assertRaises(dual.DualSourceConflict):
            self.check(current=current)

    def test_old_authority_cannot_have_maximum_sequence(self):
        old=self.old.copy()
        old['sequence_a']=live.MAX_SEQUENCE
        with self.assertRaises(dual.DualSourceConflict):
            self.check(old=old)

    def test_two_sources_cannot_share_authority_identity(self):
        other=self.source_b.copy()
        other['authority_id']=self.source_a['authority_id']
        with self.assertRaises(dual.DualSourceConflict):
            self.check(source_b=other)

    def test_two_sources_cannot_share_dns_host(self):
        other=self.source_b.copy()
        other['source_url']='https://source-a.example.org/other'
        with self.assertRaises(dual.DualSourceConflict):
            self.check(source_b=other)

    def test_two_sources_cannot_share_ed25519_identity(self):
        other=self.source_b.copy()
        other['authority_public']=self.source_a['authority_public']
        other['authority_pin']=self.source_a['authority_pin']
        with self.assertRaises(dual.DualSourceConflict):
            self.check(source_b=other)

    def test_authority_cannot_equal_stage_w_notary(self):
        other=self.notaries.copy()
        other['notary_a_public']=self.source_b['authority_public']
        other['notary_a_pin']=self.source_b['authority_pin']
        with self.assertRaises(dual.DualSourceConflict):
            self.check(notaries=other)

    def test_changed_independently_pinned_public_key_refused(self):
        other=self.source_b.copy()
        other['authority_pin']='f'*64
        with self.assertRaises(dual.DualSourceConflict):
            self.check(source_b=other)

    def test_old_challenge_collision_refused(self):
        old=self.old.copy()
        old['challenge_b']=old['challenge_a']
        with self.assertRaises(dual.DualSourceConflict):
            self.check(old=old)

    def test_new_challenge_equal_previous_rejected(self):
        with self.assertRaises(dual.DualSourceConflict):
            self.check(challenges=('c'*32,self.old['challenge_a']))

    def test_same_new_challenge_both_sources_rejected(self):
        with self.assertRaises(dual.DualSourceConflict):
            self.check(challenges=('c'*32,'c'*32))

    def test_second_authority_has_different_new_witness_refused(self):
        def fetch(url,scope,nonce):
            if url==self.source_b['source_url']:
                return self.sign(self.source_b,1,self.current,
                           challenge=nonce,sequence=12,
                           latest_witness_sha256='f'*64)
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceConflict):
            self.check(fetcher=fetch)

    def test_second_authority_unavailable_no_partial_quorum(self):
        def fetch(url,scope,nonce):
            if url==self.source_b['source_url']:
                raise live.LiveSourceUnavailable('offline')
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceUnavailable):
            self.check(fetcher=fetch)

    def test_invalid_new_signature_fails_closed(self):
        def fetch(url,scope,nonce):
            raw=self.fetch(url,scope,nonce)
            if url==self.source_a['source_url']:
                item=json.loads(raw)
                item['signature_hex']='0'*128
                return json.dumps(item).encode()
            return raw
        with self.assertRaises(ValueError):
            self.check(fetcher=fetch)

    def test_proposed_checkpoint_is_not_externally_retained(self):
        report=self.check()
        self.assertFalse(report['external_store_commit_or_readback_proved'])
        self.assertFalse(report['physical_or_administrative_independence_proved'])
        self.assertFalse(report['compromised_both_sources_rollback_excluded'])

    def test_missing_signed_original_pair_is_refused(self):
        with self.assertRaises(dual.DualSourceConflict):
            self.check(old_signed_a=b'')

    def test_cli_unavailability_is_redacted_and_never_retires_fence(self):
        oldfiles=[]
        for index,raw in enumerate((self.old_raw_a,self.old_raw_b)):
            path=Path(self.temp.name)/('old-%d' % index)
            path.write_bytes(raw)
            path.chmod(0o600)
            oldfiles.append(path)
        argv=[]
        for name,source,path in zip(('a','b'),
                                    (self.source_a,self.source_b),oldfiles):
            argv += [
                '--source-'+name+'-url',source['source_url'],
                '--source-'+name+'-id',source['authority_id'],
                '--source-'+name+'-public',str(source['authority_public']),
                '--source-'+name+'-pin',source['authority_pin'],
                '--old-'+name+'-signed',str(path),
                '--old-'+name+'-challenge',self.old['challenge_'+name],
                '--old-'+name+'-sequence',str(self.old['sequence_'+name])]
        for role in ('a','b'):
            argv += ['--notary-'+role+'-public',
                     str(self.notaries['notary_'+role+'_public']),
                     '--notary-'+role+'-pin',
                     self.notaries['notary_'+role+'_pin']]
        for name,state in (('old',self.old),('new',self.current)):
            argv+=['--'+name+'-count',str(state['count'])]
            for key in ('head','history','witness','bundle'):
                argv+=['--'+name+'-'+key+'-sha256',state[key]]
        argv+=['--scope',self.scope,
               '--old-checkpoint-sha256',self.pin]
        with mock.patch.object(live,'fetch_live_receipt',
                side_effect=live.LiveSourceUnavailable('offline')):
            with contextlib.redirect_stdout(output:=io.StringIO()):
                code=dual.main(argv)
        self.assertEqual(code,2)
        result=json.loads(output.getvalue())
        self.assertTrue(result['authority_unavailable'])
        self.assertFalse(result['witness_fence_retired'])
        self.assertNotIn('challenge_nonce',output.getvalue())


if __name__=='__main__':
    unittest.main()
