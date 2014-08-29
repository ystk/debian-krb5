#!/usr/bin/python
from k5test import *

# Skip this test if pkinit wasn't built.
if not os.path.exists(os.path.join(plugins, 'preauth', 'pkinit.so')):
    success('Warning: not testing pkinit because it is not built')
    exit(0)

# Check if soft-pkcs11.so is available.
try:
    import ctypes
    lib = ctypes.LibraryLoader(ctypes.CDLL).LoadLibrary('soft-pkcs11.so')
    del lib
    have_soft_pkcs11 = True
except:
    have_soft_pkcs11 = False

# Construct a krb5.conf fragment configuring pkinit.
certs = os.path.join(srctop, 'tests', 'dejagnu', 'pkinit-certs')
ca_pem = os.path.join(certs, 'ca.pem')
kdc_pem = os.path.join(certs, 'kdc.pem')
user_pem = os.path.join(certs, 'user.pem')
privkey_pem = os.path.join(certs, 'privkey.pem')
privkey_enc_pem = os.path.join(certs, 'privkey-enc.pem')
user_p12 = os.path.join(certs, 'user.p12')
user_enc_p12 = os.path.join(certs, 'user-enc.p12')
path = os.path.join(os.getcwd(), 'testdir', 'tmp-pkinit-certs')
path_enc = os.path.join(os.getcwd(), 'testdir', 'tmp-pkinit-certs-enc')

pkinit_krb5_conf = {'realms': {'$realm': {
            'pkinit_anchors': 'FILE:%s' % ca_pem}}}
pkinit_kdc_conf = {'realms': {'$realm': {
            'default_principal_flags': '+preauth',
            'pkinit_eku_checking': 'none',
            'pkinit_identity': 'FILE:%s,%s' % (kdc_pem, privkey_pem)}}}
restrictive_kdc_conf = {'realms': {'$realm': {
            'restrict_anonymous_to_tgt': 'true' }}}

file_identity = 'FILE:%s,%s' % (user_pem, privkey_pem)
file_enc_identity = 'FILE:%s,%s' % (user_pem, privkey_enc_pem)
dir_identity = 'DIR:%s' % path
dir_enc_identity = 'DIR:%s' % path_enc
dir_file_identity = 'FILE:%s,%s' % (os.path.join(path, 'user.crt'),
                                    os.path.join(path, 'user.key'))
dir_file_enc_identity = 'FILE:%s,%s' % (os.path.join(path_enc, 'user.crt'),
                                        os.path.join(path_enc, 'user.key'))
p12_identity = 'PKCS12:%s' % user_p12
p12_enc_identity = 'PKCS12:%s' % user_enc_p12
p11_identity = 'PKCS11:soft-pkcs11.so'
p11_token_identity = ('PKCS11:module_name=soft-pkcs11.so:'
                      'slotid=1:token=SoftToken (token)')

realm = K5Realm(krb5_conf=pkinit_krb5_conf, kdc_conf=pkinit_kdc_conf,
                get_creds=False)

# Sanity check - password-based preauth should still work.
realm.run(['./responder',
           '-r', 'password=%s' % password('user'),
           'user@%s' % realm.realm])
realm.kinit('user@%s' % realm.realm,
            password=password('user'))
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# Test anonymous PKINIT.
out = realm.kinit('@%s' % realm.realm, flags=['-n'], expected_code=1)
if 'not found in Kerberos database' not in out:
    fail('Wrong error for anonymous PKINIT without anonymous enabled')
realm.addprinc('WELLKNOWN/ANONYMOUS')
realm.kinit('@%s' % realm.realm, flags=['-n'])
realm.klist('WELLKNOWN/ANONYMOUS@WELLKNOWN:ANONYMOUS')
realm.run([kvno, realm.host_princ])

# Test with anonymous restricted; FAST should work but kvno should fail.
r_env = realm.special_env('restrict', True, kdc_conf=restrictive_kdc_conf)
realm.stop_kdc()
realm.start_kdc(env=r_env)
realm.kinit('@%s' % realm.realm, flags=['-n'])
realm.kinit('@%s' % realm.realm, flags=['-n', '-T', realm.ccache])
out = realm.run([kvno, realm.host_princ], expected_code=1)
if 'KDC policy rejects request' not in out:
    fail('Wrong error for restricted anonymous PKINIT')

# Go back to a normal KDC and disable anonymous PKINIT.
realm.stop_kdc()
realm.start_kdc()
realm.run_kadminl('delprinc -force WELLKNOWN/ANONYMOUS')

# Run the basic test - PKINIT with FILE: identity, with no password on the key.
realm.run(['./responder',
           '-x',
           'pkinit=',
           '-X',
           'X509_user_identity=%s' % file_identity,
           'user@%s' % realm.realm])
realm.kinit('user@%s' % realm.realm,
            flags=['-X', 'X509_user_identity=%s' % file_identity])
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# Run the basic test - PKINIT with FILE: identity, with a password on the key,
# supplied by the prompter.
# Expect failure if the responder does nothing, and we have no prompter.
realm.run(['./responder',
          '-x',
          'pkinit={"%s": 0}' % file_enc_identity,
          '-X',
          'X509_user_identity=%s' % file_enc_identity,
          'user@%s' % realm.realm],
          expected_code=2)
realm.kinit('user@%s' % realm.realm,
            flags=['-X', 'X509_user_identity=%s' % file_enc_identity],
            password='encrypted')
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# Run the basic test - PKINIT with FILE: identity, with a password on the key,
# supplied by the responder.
# Supply the response in raw form.
realm.run(['./responder',
           '-x',
           'pkinit={"%s": 0}' % file_enc_identity,
           '-r',
           'pkinit={"%s": "encrypted"}' % file_enc_identity,
           '-X',
           'X509_user_identity=%s' % file_enc_identity,
           'user@%s' % realm.realm])
# Supply the response through the convenience API.
realm.run(['./responder',
           '-X',
           'X509_user_identity=%s' % file_enc_identity,
           '-p',
           '%s=%s' % (file_enc_identity, 'encrypted'),
           'user@%s' % realm.realm])
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# PKINIT with DIR: identity, with no password on the key.
os.mkdir(path)
os.mkdir(path_enc)
shutil.copy(privkey_pem, os.path.join(path, 'user.key'))
shutil.copy(privkey_enc_pem, os.path.join(path_enc, 'user.key'))
shutil.copy(user_pem, os.path.join(path, 'user.crt'))
shutil.copy(user_pem, os.path.join(path_enc, 'user.crt'))
realm.run(['./responder',
           '-x',
           'pkinit=',
           '-X',
           'X509_user_identity=%s' % dir_identity,
           'user@%s' % realm.realm])
realm.kinit('user@%s' % realm.realm,
            flags=['-X', 'X509_user_identity=%s' % dir_identity])
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# PKINIT with DIR: identity, with a password on the key, supplied by the
# prompter.
# Expect failure if the responder does nothing, and we have no prompter.
realm.run(['./responder',
           '-x',
           'pkinit={"%s": 0}' %
           dir_file_enc_identity,
           '-X',
           'X509_user_identity=%s' % dir_enc_identity,
           'user@%s' % realm.realm],
           expected_code=2)
realm.kinit('user@%s' % realm.realm,
            flags=['-X', 'X509_user_identity=%s' % dir_enc_identity],
            password='encrypted')
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# PKINIT with DIR: identity, with a password on the key, supplied by the
# responder.
# Supply the response in raw form.
realm.run(['./responder',
           '-x',
           'pkinit={"%s": 0}' %
           dir_file_enc_identity,
           '-r',
           'pkinit={"%s": "encrypted"}' % dir_file_enc_identity,
           '-X',
           'X509_user_identity=%s' % dir_enc_identity,
           'user@%s' % realm.realm])
# Supply the response through the convenience API.
realm.run(['./responder',
           '-X',
           'X509_user_identity=%s' % dir_enc_identity,
           '-p',
           '%s=%s' % (dir_file_enc_identity, 'encrypted'),
           'user@%s' % realm.realm])
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# PKINIT with PKCS12: identity, with no password on the bundle.
realm.run(['./responder',
           '-x',
           'pkinit=',
           '-X',
           'X509_user_identity=%s' % p12_identity,
           'user@%s' % realm.realm])
realm.kinit('user@%s' % realm.realm,
            flags=['-X', 'X509_user_identity=%s' % p12_identity])
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# PKINIT with PKCS12: identity, with a password on the bundle, supplied by the
# prompter.
# Expect failure if the responder does nothing, and we have no prompter.
realm.run(['./responder',
           '-x',
           'pkinit={"%s": 0}' % p12_enc_identity,
           '-X',
           'X509_user_identity=%s' % p12_enc_identity,
           'user@%s' % realm.realm],
           expected_code=2)
realm.kinit('user@%s' % realm.realm,
            flags=['-X', 'X509_user_identity=%s' % p12_enc_identity],
            password='encrypted')
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

# PKINIT with PKCS12: identity, with a password on the bundle, supplied by the
# responder.
# Supply the response in raw form.
realm.run(['./responder',
           '-x',
           'pkinit={"%s": 0}' % p12_enc_identity,
           '-r',
           'pkinit={"%s": "encrypted"}' % p12_enc_identity,
           '-X',
           'X509_user_identity=%s' % p12_enc_identity,
           'user@%s' % realm.realm])
# Supply the response through the convenience API.
realm.run(['./responder',
           '-X',
           'X509_user_identity=%s' % p12_enc_identity,
           '-p',
           '%s=%s' % (p12_enc_identity, 'encrypted'),
           'user@%s' % realm.realm])
realm.klist('user@%s' % realm.realm)
realm.run([kvno, realm.host_princ])

if have_soft_pkcs11:
    softpkcs11rc = os.path.join(os.getcwd(), 'testdir', 'soft-pkcs11.rc')
    realm.env['SOFTPKCS11RC'] = softpkcs11rc

    # PKINIT with PKCS11: identity, with no need for a PIN.
    conf = open(softpkcs11rc, 'w')
    conf.write("%s\t%s\t%s\t%s\n" % ('user', 'user token', user_pem,
                                     privkey_pem))
    conf.close()
    # Expect to succeed without having to supply any more information.
    realm.run(['./responder',
               '-x',
               'pkinit=',
               '-X',
               'X509_user_identity=%s' % p11_identity,
               'user@%s' % realm.realm])
    realm.kinit('user@%s' % realm.realm,
                flags=['-X', 'X509_user_identity=%s' % p11_identity])
    realm.klist('user@%s' % realm.realm)
    realm.run([kvno, realm.host_princ])

    # PKINIT with PKCS11: identity, with a PIN supplied by the prompter.
    os.remove(softpkcs11rc)
    conf = open(softpkcs11rc, 'w')
    conf.write("%s\t%s\t%s\t%s\n" % ('user', 'user token', user_pem,
                                     privkey_enc_pem))
    conf.close()
    # Expect failure if the responder does nothing, and there's no prompter
    realm.run(['./responder',
               '-x',
               'pkinit={"%s": 0}' % p11_token_identity,
               '-X',
               'X509_user_identity=%s' % p11_identity,
               'user@%s' % realm.realm],
               expected_code=2)
    realm.kinit('user@%s' % realm.realm,
                flags=['-X', 'X509_user_identity=%s' % p11_identity],
                password='encrypted')
    realm.klist('user@%s' % realm.realm)
    realm.run([kvno, realm.host_princ])

    # PKINIT with PKCS11: identity, with a PIN supplied by the responder.
    # Supply the response in raw form.
    realm.run(['./responder',
               '-x',
               'pkinit={"%s": 0}' % p11_token_identity,
               '-r',
               'pkinit={"%s": "encrypted"}' %
               p11_token_identity,
               '-X',
               'X509_user_identity=%s' % p11_identity,
               'user@%s' % realm.realm])
    # Supply the response through the convenience API.
    realm.run(['./responder',
               '-X',
               'X509_user_identity=%s' % p11_identity,
               '-p',
               '%s=%s' % (p11_token_identity, 'encrypted'),
               'user@%s' % realm.realm])
    realm.klist('user@%s' % realm.realm)
    realm.run([kvno, realm.host_princ])
else:
    output('soft-pkcs11.so not found: skipping tests with PKCS11 identities\n')

success('Authenticated PKINIT')
