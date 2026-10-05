import test from 'node:test';
import assert from 'node:assert/strict';
import { buildStudentEmail, changeDomain, validLocalPart } from '../static/domain.js';
const dut = {
  id: 3,
  name: 'DUT',
  shortName: 'DUT',
  studentEmailDomain: 'dut4life.ac.za',
  isActive: true,
};
test('builds normalized institutional email', () =>
  assert.equal(buildStudentEmail(' 221AbC ', dut), '221abc@dut4life.ac.za'));
test('domain changes preserve local part', () => {
  const result = changeDomain('221234567', { ...dut, studentEmailDomain: 'tuks.co.za' });
  assert.equal(result.local, '221234567');
  assert.equal(result.suffix, '@tuks.co.za');
  assert.match(result.example, /221234567@tuks.co.za/);
});
test('rejects full addresses and malformed local parts', () => {
  for (const value of ['name@gmail.com', 'with space', ''])
    assert.equal(validLocalPart(value), false);
  assert.equal(validLocalPart('221.test+study'), true);
});
