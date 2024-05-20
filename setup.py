from setuptools import setup, find_packages

test_deps = ["pytest"]
extras = {'test': test_deps}

setup(
    name='git_trunk',
    use_scm_version=True,
    packages=find_packages(),
    license='LGPLv3',
    url='https://github.com/focusate/git-trunk',
    description="Git Trunk based workflow",
    long_description=open('README.rst').read(),
    install_requires=['footil>=0.24.0', 'gitpython'],
    tests_require=test_deps,
    extras_require=extras,
    setup_requires=[
        'setuptools_scm',
    ],
    scripts=['bin/git-trunk'],
    maintainer='Andrius Laukavičius',
    maintainer_email='andrius@timefordev.com',
    python_requires='>=3.8',
    classifiers=[
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development',
        'Topic :: Utilities',
    ],
)
